"""Conservative deterministic resolution policy for BCI Historical v0.1."""

from __future__ import annotations

from uuid import UUID, NAMESPACE_URL, uuid5

from ..models import (
    BciHistoricalPdfRecordEvidence,
    FinancialObservation,
    ImportBatch,
    Movement,
    ObservationResolution,
    RawRecord,
)
from . import observation_resolution


POLICY_NAME = "bci_historical_reconciled"
POLICY_VERSION = "v1"
POLICY_NAMESPACE = uuid5(NAMESPACE_URL, "gouda/bci-historical-policy/v1")
OBSERVATION_METHOD = "bci_historical_current_account_pdf"
OBSERVATION_VERSION = "bci-historical-current-account-pdf-v1"


def resolve_bci_historical_observation(
    *,
    observation_id: UUID,
) -> ObservationResolution | None:
    """Confirm one eligible observation, or abstain without changing state."""

    observation = (
        FinancialObservation.objects.select_related(
            "raw_record__import_batch",
        )
        .filter(pk=observation_id)
        .first()
    )
    if observation is None:
        return None
    batch = observation.raw_record.import_batch
    if (
        batch.source_kind != ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF
        or batch.status != ImportBatch.Status.ACCEPTED
        or batch.reconciliation_status != ImportBatch.ReconciliationStatus.RECONCILED
        or observation.state != FinancialObservation.State.UNRESOLVED
        or observation.accounting_date is None
        or not _matches_bci_record_evidence(observation)
    ):
        return None

    candidate_qs = Movement.objects.filter(
        account_id=observation.account_id,
        occurrence_date=observation.accounting_date,
        signed_amount=observation.signed_amount,
        currency=observation.currency,
    )
    candidate_ids = frozenset(candidate_qs.values_list("raw_record_id", flat=True))
    collision_override = False
    if candidate_ids:
        collision_override = _safe_same_statement_collision(
            observation,
            batch_id=batch.pk,
            candidate_raw_record_ids=candidate_ids,
        )
        if not collision_override:
            return None

    try:
        return _confirm_observation(
            observation,
            collision_override=collision_override,
            candidate_raw_record_ids=candidate_ids if collision_override else None,
        )
    except observation_resolution.ObservationServiceError as error:
        if error.code == "movement_candidate_exists":
            # Another same-account resolver may have created the first
            # same-statement Movement after the initial candidate read. Re-read
            # the candidate set and apply the same external-candidate guard.
            retry_candidate_ids = _candidate_raw_record_ids(observation)
            if retry_candidate_ids and _safe_same_statement_collision(
                observation,
                batch_id=batch.pk,
                candidate_raw_record_ids=retry_candidate_ids,
            ):
                try:
                    return _confirm_observation(
                        observation,
                        collision_override=True,
                        candidate_raw_record_ids=retry_candidate_ids,
                    )
                except observation_resolution.ObservationServiceError as retry_error:
                    if retry_error.code in {"movement_candidate_exists", "observation_transition_invalid", "origin_movement_exists"}:
                        return None
                    raise
            return None
        if error.code in {"observation_transition_invalid", "origin_movement_exists"}:
            return None
        raise


def _confirm_observation(
    observation: FinancialObservation,
    *,
    collision_override: bool,
    candidate_raw_record_ids: frozenset[UUID] | None,
) -> ObservationResolution:
    reason_code = "same_statement_distinct_ordered_row" if collision_override else "reconciled_historical_new"
    key = uuid5(
        POLICY_NAMESPACE,
        f"{observation.pk}:{observation.account_id}:{POLICY_NAME}:{POLICY_VERSION}:{reason_code}",
    )
    return observation_resolution.confirm_new(
        observation_id=observation.pk,
        occurrence_date=observation.accounting_date,
        decision_source=ObservationResolution.DecisionSource.DETERMINISTIC_POLICY,
        policy_name=POLICY_NAME,
        policy_version=POLICY_VERSION,
        reason_code=reason_code,
        idempotency_key=key,
        allow_exact_collision=collision_override,
        allowed_collision_raw_record_ids=candidate_raw_record_ids,
    )


def _candidate_raw_record_ids(observation: FinancialObservation) -> frozenset[UUID]:
    return frozenset(
        Movement.objects.filter(
            account_id=observation.account_id,
            occurrence_date=observation.accounting_date,
            signed_amount=observation.signed_amount,
            currency=observation.currency,
        ).values_list("raw_record_id", flat=True)
    )


def _matches_bci_record_evidence(observation: FinancialObservation) -> bool:
    raw_record = observation.raw_record
    if (
        raw_record.record_kind != RawRecord.RecordKind.BCI_HISTORICAL_PDF_RECORD
        or raw_record.parse_outcome != RawRecord.ParseOutcome.PARSED
        or observation.transaction_date is not None
        or observation.interpretation_method != OBSERVATION_METHOD
        or observation.interpretation_version != OBSERVATION_VERSION
    ):
        return False
    evidence = BciHistoricalPdfRecordEvidence.objects.filter(raw_record_id=raw_record.pk).first()
    return (
        evidence is not None
        and evidence.transaction_date is None
        and evidence.accounting_date == observation.accounting_date
        and evidence.signed_amount == observation.signed_amount
        and evidence.currency == observation.currency
    )


def resolve_bci_historical_batch(*, import_batch_id: UUID) -> tuple[ObservationResolution, ...]:
    """Resolve eligible observations in deterministic source-row order."""

    observations = FinancialObservation.objects.filter(
        raw_record__import_batch_id=import_batch_id,
        state=FinancialObservation.State.UNRESOLVED,
    ).order_by("raw_record__record_ordinal", "pk")
    resolutions = []
    for observation in observations:
        resolution = resolve_bci_historical_observation(observation_id=observation.pk)
        if resolution is not None:
            resolutions.append(resolution)
    return tuple(resolutions)


def _safe_same_statement_collision(
    observation: FinancialObservation,
    *,
    batch_id: UUID,
    candidate_raw_record_ids: frozenset[UUID],
) -> bool:
    if not candidate_raw_record_ids:
        return False
    rows = list(
        BciHistoricalPdfRecordEvidence.objects.filter(
            raw_record_id__in=candidate_raw_record_ids,
            raw_record__import_batch_id=batch_id,
            raw_record__parse_outcome="PARSED",
            accounting_date=observation.accounting_date,
            signed_amount=observation.signed_amount,
            currency=observation.currency,
            running_balance__isnull=False,
        ).values_list("raw_record_id", "source_row_ordinal")
    )
    if len(rows) != len(candidate_raw_record_ids) or any(row_ordinal is None for _, row_ordinal in rows):
        return False
    row_ordinals = {row_ordinal for _, row_ordinal in rows}
    if len(row_ordinals) != len(rows):
        return False
    current = BciHistoricalPdfRecordEvidence.objects.filter(
        raw_record_id=observation.raw_record_id,
        raw_record__import_batch_id=batch_id,
        raw_record__parse_outcome="PARSED",
        accounting_date=observation.accounting_date,
        signed_amount=observation.signed_amount,
        currency=observation.currency,
        running_balance__isnull=False,
    ).values_list("source_row_ordinal", flat=True).first()
    return current is not None and current not in row_ordinals
