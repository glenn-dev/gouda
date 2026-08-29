"""Deterministic FinancialObservation creation and resolution boundary."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
import unicodedata
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from ..models import (
    Account,
    FinancialObservation,
    Movement,
    ObservationResolution,
    RawRecord,
)
from ..validation import validate_exact_money


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

OBSERVATION_TRANSITIONS = {
    ObservationResolution.Action.CONFIRM_NEW: {
        FinancialObservation.State.UNRESOLVED: FinancialObservation.State.RESOLVED,
    },
    ObservationResolution.Action.MATCH_EXISTING: {
        FinancialObservation.State.UNRESOLVED: FinancialObservation.State.RESOLVED,
    },
    ObservationResolution.Action.REJECT: {
        FinancialObservation.State.UNRESOLVED: FinancialObservation.State.REJECTED,
    },
    ObservationResolution.Action.MARK_CONFLICT: {
        FinancialObservation.State.UNRESOLVED: FinancialObservation.State.CONFLICT,
        FinancialObservation.State.RESOLVED: FinancialObservation.State.CONFLICT,
    },
    ObservationResolution.Action.REOPEN: {
        FinancialObservation.State.REJECTED: FinancialObservation.State.UNRESOLVED,
        FinancialObservation.State.CONFLICT: FinancialObservation.State.UNRESOLVED,
    },
    ObservationResolution.Action.SUPERSEDE: {
        FinancialObservation.State.UNRESOLVED: FinancialObservation.State.SUPERSEDED,
        FinancialObservation.State.RESOLVED: FinancialObservation.State.SUPERSEDED,
        FinancialObservation.State.REJECTED: FinancialObservation.State.SUPERSEDED,
        FinancialObservation.State.CONFLICT: FinancialObservation.State.SUPERSEDED,
    },
}


class ObservationServiceError(ValueError):
    """A deterministic observation-boundary failure with a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def create_financial_observation(
    *,
    raw_record_id: UUID,
    account_id: UUID,
    transaction_date: date | None,
    accounting_date: date | None,
    signed_amount: Decimal,
    currency: str,
    description: str | None,
    source_reference: str | None,
    interpretation_method: str,
    interpretation_version: str,
    idempotency_key: UUID,
) -> FinancialObservation:
    """Create one immutable unresolved claim, or return its exact retry."""

    _require_outside_transaction()
    raw_record_id = _require_uuid(raw_record_id, "raw_record_id_invalid")
    account_id = _require_uuid(account_id, "account_id_invalid")
    idempotency_key = _require_uuid(idempotency_key, "idempotency_key_invalid")
    transaction_date = _optional_date(transaction_date, "transaction_date_invalid")
    accounting_date = _optional_date(accounting_date, "accounting_date_invalid")
    if transaction_date is None and accounting_date is None:
        _fail("financial_date_missing")
    _validate_signed_amount(signed_amount)
    currency = _validate_currency(currency)
    description = _normalize_optional_text(description, "description_invalid")
    source_reference = _normalize_optional_text(source_reference, "source_reference_invalid")
    interpretation_method = _normalize_identifier(
        interpretation_method,
        "interpretation_method_invalid",
    )
    interpretation_version = _normalize_identifier(
        interpretation_version,
        "interpretation_version_invalid",
    )
    expected = {
        "raw_record_id": raw_record_id,
        "account_id": account_id,
        "transaction_date": transaction_date,
        "accounting_date": accounting_date,
        "signed_amount": signed_amount,
        "currency": currency,
        "description": description,
        "source_reference": source_reference,
        "interpretation_method": interpretation_method,
        "interpretation_version": interpretation_version,
    }

    existing = FinancialObservation.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        _assert_observation_retry(existing, expected)
        return existing

    try:
        with transaction.atomic():
            try:
                account = Account.objects.select_for_update().get(pk=account_id)
            except Account.DoesNotExist:
                _fail("account_not_found")
            existing = FinancialObservation.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                _assert_observation_retry(existing, expected)
                return existing
            try:
                raw_record = RawRecord.objects.select_related("import_batch").get(pk=raw_record_id)
            except RawRecord.DoesNotExist:
                _fail("raw_record_not_found")
            if raw_record.parse_outcome != RawRecord.ParseOutcome.PARSED:
                _fail("raw_record_not_parsed")
            if raw_record.import_batch.account_id != account.pk:
                _fail("raw_record_account_mismatch")
            if currency != account.currency:
                _fail("account_currency_mismatch")

            observation = FinancialObservation(
                raw_record=raw_record,
                account=account,
                transaction_date=transaction_date,
                accounting_date=accounting_date,
                signed_amount=signed_amount,
                currency=currency,
                description=description,
                source_reference=source_reference,
                interpretation_method=interpretation_method,
                interpretation_version=interpretation_version,
                idempotency_key=idempotency_key,
                state=FinancialObservation.State.UNRESOLVED,
                current_movement=None,
                state_version=0,
            )
            observation.full_clean()
            observation.save()
            return observation
    except ObservationServiceError:
        raise
    except IntegrityError:
        existing = FinancialObservation.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            _assert_observation_retry(existing, expected)
            return existing
        raise ObservationServiceError("observation_integrity_error") from None


def confirm_new(
    *,
    observation_id: UUID,
    occurrence_date: date,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
    allow_exact_collision: bool = False,
    allowed_collision_raw_record_ids: frozenset[UUID] | None = None,
) -> ObservationResolution:
    """Confirm one unresolved observation as one new canonical Movement.

    ``allow_exact_collision`` means the caller independently established that
    an exact collision candidate is a distinct event. The collision tuple does
    not become economic-event identity and no existing Movement is attached.
    """

    occurrence_date = _required_date(occurrence_date, "occurrence_date_invalid")
    allow_exact_collision = _required_bool(
        allow_exact_collision,
        "allow_exact_collision_invalid",
    )
    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.CONFIRM_NEW,
        movement_id=None,
        successor_observation_id=None,
        occurrence_date=occurrence_date,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=allow_exact_collision,
        allowed_collision_raw_record_ids=allowed_collision_raw_record_ids,
    )


def match_existing(
    *,
    observation_id: UUID,
    movement_id: UUID,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
) -> ObservationResolution:
    """Validate explicit support using only generic hard incompatibilities.

    The caller's policy selects the target. Date, description, and reference
    evidence remain policy context rather than generic event identity.
    """

    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.MATCH_EXISTING,
        movement_id=movement_id,
        successor_observation_id=None,
        occurrence_date=None,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=False,
    )


def reject(
    *,
    observation_id: UUID,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
) -> ObservationResolution:
    """Reject an unresolved observation without changing canonical data."""

    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.REJECT,
        movement_id=None,
        successor_observation_id=None,
        occurrence_date=None,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=False,
    )


def mark_conflict(
    *,
    observation_id: UUID,
    movement_id: UUID,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
) -> ObservationResolution:
    """Record a conflict with a known Movement without altering it."""

    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.MARK_CONFLICT,
        movement_id=movement_id,
        successor_observation_id=None,
        occurrence_date=None,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=False,
    )


def reopen(
    *,
    observation_id: UUID,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
) -> ObservationResolution:
    """Explicitly reopen a rejected or conflicted observation."""

    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.REOPEN,
        movement_id=None,
        successor_observation_id=None,
        occurrence_date=None,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=False,
    )


def supersede(
    *,
    observation_id: UUID,
    successor_observation_id: UUID,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
) -> ObservationResolution:
    """Supersede an immutable claim with a new unresolved interpretation."""

    return _execute_transition(
        observation_id=observation_id,
        action=ObservationResolution.Action.SUPERSEDE,
        movement_id=None,
        successor_observation_id=successor_observation_id,
        occurrence_date=None,
        decision_source=decision_source,
        policy_name=policy_name,
        policy_version=policy_version,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        allow_exact_collision=False,
    )


def _execute_transition(
    *,
    observation_id: UUID,
    action: str,
    movement_id: UUID | None,
    successor_observation_id: UUID | None,
    occurrence_date: date | None,
    decision_source: str,
    policy_name: str,
    policy_version: str,
    reason_code: str,
    idempotency_key: UUID,
    allow_exact_collision: bool,
    allowed_collision_raw_record_ids: frozenset[UUID] | None = None,
) -> ObservationResolution:
    _require_outside_transaction()
    observation_id = _require_uuid(observation_id, "observation_id_invalid")
    movement_id = (
        _require_uuid(movement_id, "movement_id_invalid") if movement_id is not None else None
    )
    successor_observation_id = (
        _require_uuid(successor_observation_id, "successor_observation_id_invalid")
        if successor_observation_id is not None
        else None
    )
    idempotency_key = _require_uuid(idempotency_key, "idempotency_key_invalid")
    decision_source = _validate_decision_source(decision_source)
    policy_name = _normalize_identifier(policy_name, "policy_name_invalid")
    policy_version = _normalize_identifier(policy_version, "policy_version_invalid")
    reason_code = _normalize_identifier(reason_code, "reason_code_invalid")

    expected = {
        "observation_id": observation_id,
        "action": action,
        "movement_id": movement_id,
        "successor_observation_id": successor_observation_id,
        "decision_source": decision_source,
        "policy_name": policy_name,
        "policy_version": policy_version,
        "reason_code": reason_code,
        "occurrence_date": occurrence_date,
    }
    existing = ObservationResolution.objects.select_related("movement").filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        _assert_resolution_retry(existing, expected)
        return existing

    account_id = FinancialObservation.objects.filter(pk=observation_id).values_list(
        "account_id", flat=True
    ).first()
    if account_id is None:
        _fail("observation_not_found")

    try:
        with transaction.atomic():
            try:
                account = Account.objects.select_for_update().get(pk=account_id)
            except Account.DoesNotExist:
                _fail("account_not_found")
            try:
                observation = (
                    FinancialObservation.objects.select_for_update()
                    .select_related("raw_record__import_batch")
                    .get(pk=observation_id)
                )
            except FinancialObservation.DoesNotExist:
                _fail("observation_not_found")
            if observation.account_id != account.pk:
                _fail("observation_account_changed")

            existing = ObservationResolution.objects.select_related("movement").filter(
                idempotency_key=idempotency_key
            ).first()
            if existing is not None:
                _assert_resolution_retry(existing, expected)
                return existing

            movement = None
            successor = None
            from_state = observation.state
            to_state = _transition_target(action, from_state)

            if action == ObservationResolution.Action.CONFIRM_NEW:
                assert occurrence_date is not None
                _require_observation_date(observation, occurrence_date)
                if Movement.objects.filter(raw_record_id=observation.raw_record_id).exists():
                    _fail("origin_movement_exists")
                candidates = Movement.objects.filter(
                    account=account,
                    occurrence_date=occurrence_date,
                    signed_amount=observation.signed_amount,
                    currency=observation.currency,
                )
                candidate_ids = frozenset(candidates.values_list("raw_record_id", flat=True))
                if candidate_ids:
                    if not allow_exact_collision:
                        _fail("movement_candidate_exists")
                    if allowed_collision_raw_record_ids is not None and candidate_ids != allowed_collision_raw_record_ids:
                        _fail("movement_candidate_exists")
                movement = Movement(
                    raw_record=observation.raw_record,
                    account=account,
                    occurrence_date=occurrence_date,
                    signed_amount=observation.signed_amount,
                    currency=observation.currency,
                    description=observation.description,
                    source_reference=observation.source_reference,
                    running_balance=None,
                )
                movement.full_clean()
                movement.save()
            elif action == ObservationResolution.Action.MATCH_EXISTING:
                movement = _lock_movement(movement_id)
                _validate_support_match(observation, movement)
            elif action == ObservationResolution.Action.REJECT:
                pass
            elif action == ObservationResolution.Action.MARK_CONFLICT:
                movement = _lock_movement(movement_id)
                _validate_movement_context(observation, movement)
                if (
                    observation.state == FinancialObservation.State.RESOLVED
                    and observation.current_movement_id != movement.pk
                ):
                    _fail("conflict_movement_mismatch")
            elif action == ObservationResolution.Action.REOPEN:
                movement = (
                    _lock_movement(observation.current_movement_id)
                    if observation.current_movement_id is not None
                    else None
                )
            elif action == ObservationResolution.Action.SUPERSEDE:
                successor = _lock_successor(
                    successor_observation_id,
                    account_id=observation.account_id,
                )
                _validate_successor(observation, successor)
                movement = (
                    _lock_movement(observation.current_movement_id)
                    if observation.current_movement_id is not None
                    else None
                )

            resolution = ObservationResolution(
                observation=observation,
                sequence=observation.state_version + 1,
                action=action,
                from_state=from_state,
                to_state=to_state,
                movement=movement,
                successor_observation=successor,
                decision_source=decision_source,
                policy_name=policy_name,
                policy_version=policy_version,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
            )
            resolution.full_clean()
            resolution.save()

            observation.state = to_state
            observation.current_movement = (
                movement
                if to_state in {
                    FinancialObservation.State.RESOLVED,
                    FinancialObservation.State.CONFLICT,
                }
                else None
            )
            observation.state_version += 1
            observation.full_clean()
            observation.save(
                update_fields=["state", "current_movement", "state_version"]
            )
            return resolution
    except ObservationServiceError:
        raise
    except IntegrityError:
        existing = ObservationResolution.objects.select_related("movement").filter(
            idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            _assert_resolution_retry(existing, expected)
            return existing
        raise ObservationServiceError("resolution_integrity_error") from None


def _lock_movement(movement_id: UUID | None) -> Movement:
    if movement_id is None:
        _fail("movement_id_missing")
    try:
        return Movement.objects.select_for_update().get(pk=movement_id)
    except Movement.DoesNotExist:
        raise ObservationServiceError("movement_not_found") from None


def _lock_successor(
    successor_id: UUID | None,
    *,
    account_id: UUID,
) -> FinancialObservation:
    if successor_id is None:
        _fail("successor_observation_missing")
    try:
        return (
            FinancialObservation.objects.select_for_update()
            .select_related("raw_record__import_batch")
            .get(pk=successor_id, account_id=account_id)
        )
    except FinancialObservation.DoesNotExist:
        if FinancialObservation.objects.filter(pk=successor_id).exists():
            _fail("successor_account_mismatch")
        raise ObservationServiceError("successor_observation_not_found") from None


def _validate_support_match(
    observation: FinancialObservation,
    movement: Movement,
) -> None:
    _validate_movement_context(observation, movement)
    if movement.signed_amount != observation.signed_amount:
        _fail("movement_amount_mismatch")
    originating_movement_id = Movement.objects.filter(
        raw_record_id=observation.raw_record_id
    ).values_list("pk", flat=True).first()
    if originating_movement_id is not None and originating_movement_id != movement.pk:
        _fail("origin_movement_mismatch")


def _validate_movement_context(
    observation: FinancialObservation,
    movement: Movement,
) -> None:
    if movement.account_id != observation.account_id:
        _fail("movement_account_mismatch")
    if movement.currency != observation.currency:
        _fail("movement_currency_mismatch")


def _validate_successor(
    predecessor: FinancialObservation,
    successor: FinancialObservation,
) -> None:
    if successor.pk == predecessor.pk:
        _fail("successor_observation_same")
    if successor.raw_record_id != predecessor.raw_record_id:
        _fail("successor_raw_record_mismatch")
    if successor.account_id != predecessor.account_id:
        _fail("successor_account_mismatch")
    if (
        successor.state != FinancialObservation.State.UNRESOLVED
        or successor.state_version != 0
        or successor.current_movement_id is not None
        or successor.resolutions.exists()
    ):
        _fail("successor_not_fresh")
    if successor.superseding_resolutions.exists():
        _fail("successor_already_used")
    claim_fields = (
        "transaction_date",
        "accounting_date",
        "signed_amount",
        "currency",
        "description",
        "source_reference",
        "interpretation_method",
        "interpretation_version",
    )
    if all(getattr(predecessor, field) == getattr(successor, field) for field in claim_fields):
        _fail("successor_claim_unchanged")


def _transition_target(action: str, from_state: str) -> str:
    transitions = OBSERVATION_TRANSITIONS.get(action)
    if transitions is None:
        _fail("resolution_action_invalid")
    to_state = transitions.get(from_state)
    if to_state is None:
        _fail("observation_transition_invalid")
    return to_state


def _require_observation_date(
    observation: FinancialObservation,
    candidate: date,
) -> None:
    if candidate not in {
        value
        for value in (observation.transaction_date, observation.accounting_date)
        if value is not None
    }:
        _fail("movement_date_mismatch")


def _assert_observation_retry(
    observation: FinancialObservation,
    expected: dict[str, object],
) -> None:
    if any(getattr(observation, field) != value for field, value in expected.items()):
        _fail("observation_idempotency_conflict")


def _assert_resolution_retry(
    resolution: ObservationResolution,
    expected: dict[str, object],
) -> None:
    comparable = {
        "observation_id": resolution.observation_id,
        "action": resolution.action,
        "movement_id": resolution.movement_id,
        "successor_observation_id": resolution.successor_observation_id,
        "decision_source": resolution.decision_source,
        "policy_name": resolution.policy_name,
        "policy_version": resolution.policy_version,
        "reason_code": resolution.reason_code,
    }
    for field, actual in comparable.items():
        expected_value = expected[field]
        if field == "movement_id" and expected["action"] in {
            ObservationResolution.Action.CONFIRM_NEW,
            ObservationResolution.Action.REOPEN,
            ObservationResolution.Action.SUPERSEDE,
        }:
            continue
        if actual != expected_value:
            _fail("resolution_idempotency_conflict")
    if (
        expected["action"] == ObservationResolution.Action.CONFIRM_NEW
        and resolution.movement is not None
        and resolution.movement.occurrence_date != expected["occurrence_date"]
    ):
        _fail("resolution_idempotency_conflict")


def _validate_signed_amount(value: object) -> None:
    try:
        validate_exact_money(value, field_name="signed_amount")
    except ValidationError as error:
        raise ObservationServiceError(error.code or "signed_amount_invalid") from None
    if value == 0:
        _fail("signed_amount_zero")


def _validate_currency(value: object) -> str:
    if not isinstance(value, str) or _CURRENCY_RE.fullmatch(value) is None:
        _fail("currency_invalid")
    return value


def _validate_decision_source(value: object) -> str:
    if value not in ObservationResolution.DecisionSource.values:
        _fail("decision_source_invalid")
    return value


def _normalize_identifier(value: object, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) > 64 or _IDENTIFIER_RE.fullmatch(normalized) is None:
        _fail(code)
    return normalized


def _normalize_optional_text(value: object, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(code)
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        return None
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        _fail(code)
    return normalized


def _required_date(value: object, code: str) -> date:
    result = _optional_date(value, code)
    if result is None:
        _fail(code)
    return result


def _optional_date(value: object, code: str) -> date | None:
    if value is None:
        return None
    if type(value) is not date or isinstance(value, datetime):
        _fail(code)
    return value


def _require_uuid(value: object, code: str) -> UUID:
    if not isinstance(value, UUID):
        _fail(code)
    return value


def _required_bool(value: object, code: str) -> bool:
    if type(value) is not bool:
        _fail(code)
    return value


def _require_outside_transaction() -> None:
    if transaction.get_connection().in_atomic_block:
        _fail("transaction_context_unsupported")


def _fail(code: str) -> None:
    raise ObservationServiceError(code)
