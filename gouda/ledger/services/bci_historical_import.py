"""BCI Historical current-account PDF evidence-first import service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import re
import unicodedata
from uuid import UUID, NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from gouda.bci_historical_pdf import (
    PARSER_VERSION,
    SOURCE_VARIANT,
    BciHistoricalParseResult,
    BciParserStatus,
    BciRowOutcome,
    parse_bci_historical_pdf,
)
from gouda.bci_historical_pdf.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    serialize_field_provenance_map,
)

from ..models import (
    Account,
    BciHistoricalPdfBatchEvidence,
    BciHistoricalPdfRecordEvidence,
    FinancialObservation,
    ImportBatch,
    RawRecord,
    SourceArtifact,
)
from ..validation import validate_exact_money


SOURCE_KIND_CONFLICT = "source_kind_conflict"
ACCOUNT_CONTEXT_CHANGED = "account_context_changed"
SOURCE_ACCOUNT_MISMATCH = "source_account_mismatch"
PARSER_UNEXPECTED = "bci_parser_unexpected"
MATERIALIZATION_INTEGRITY_ERROR = "bci_materialization_integrity_error"
MATERIALIZATION_DATABASE_ERROR = "bci_materialization_database_error"
MATERIALIZATION_FAILED = "bci_materialization_failed"

_SOURCE_KIND = ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF
_RECORD_KIND = RawRecord.RecordKind.BCI_HISTORICAL_PDF_RECORD
_MATERIALIZED_STATUSES = (
    ImportBatch.Status.ACCEPTED,
    ImportBatch.Status.PARTIAL,
    ImportBatch.Status.REJECTED,
)
OBSERVATION_METHOD = "bci_historical_current_account_pdf"
OBSERVATION_VERSION = PARSER_VERSION
OBSERVATION_NAMESPACE = uuid5(NAMESPACE_URL, "gouda/bci-historical-observation/v1")
_IDENTIFIER_RE = re.compile(r"^[0-9]+$")


class BciHistoricalImportServiceError(Exception):
    """Caller-facing failure containing only a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class BciHistoricalImportOperationalError(BciHistoricalImportServiceError):
    pass


@dataclass(frozen=True)
class _Registration:
    batch_id: UUID
    artifact_id: UUID
    account_id: UUID
    currency: str
    terminal: bool
    batch: ImportBatch


def import_bci_historical_current_account_pdf(
    *,
    content: bytes,
    original_filename: str,
    account: Account,
    expected_source_account_id: str,
) -> ImportBatch:
    """Register, parse, and durably preserve one BCI Historical statement.

    Parsing is performed after registration and before the materialization
    transaction. This service intentionally creates observations only; the
    source-specific resolution policy is a separate command.
    """

    if type(content) is not bytes:
        raise BciHistoricalImportServiceError("content_type_invalid")
    if not content:
        raise BciHistoricalImportServiceError("content_empty")
    if not isinstance(account, Account) or account.pk is None or account._state.adding:
        raise BciHistoricalImportServiceError("account_not_persisted")
    expected_source_account_id = _normalize_source_account_id(expected_source_account_id)
    filename = _normalize_filename(original_filename)
    if transaction.get_connection().in_atomic_block:
        raise BciHistoricalImportServiceError("transaction_context_unsupported")
    digest = hashlib.sha256(content).hexdigest()
    try:
        registration = _register(
            content=content,
            filename=filename,
            digest=digest,
            account_id=account.pk,
        )
    except BciHistoricalImportServiceError:
        raise
    except DatabaseError:
        raise BciHistoricalImportOperationalError("registration_database_error") from None
    except Exception:
        raise BciHistoricalImportOperationalError("registration_failed") from None
    if registration.terminal:
        return registration.batch

    try:
        result = parse_bci_historical_pdf(content)
    except Exception:
        return _record_fatal(registration.batch_id, "bci_parser_unexpected", None)
    if not isinstance(result, BciHistoricalParseResult):
        return _record_fatal(registration.batch_id, PARSER_UNEXPECTED, None)
    if result.status is BciParserStatus.FATAL:
        return _record_fatal(registration.batch_id, result.errors[0] if len(result.errors) == 1 else PARSER_UNEXPECTED, None)
    try:
        _validate_result(result, registration, expected_source_account_id)
        return _materialize(registration, result)
    except BciHistoricalImportServiceError as error:
        return _record_fatal(registration.batch_id, error.code, SOURCE_VARIANT)
    except IntegrityError:
        return _record_fatal(registration.batch_id, MATERIALIZATION_INTEGRITY_ERROR, SOURCE_VARIANT)
    except DatabaseError:
        return _record_fatal(registration.batch_id, MATERIALIZATION_DATABASE_ERROR, SOURCE_VARIANT)
    except Exception:
        return _record_fatal(registration.batch_id, MATERIALIZATION_FAILED, SOURCE_VARIANT)


def _register(*, content: bytes, filename: str, digest: str, account_id: UUID) -> _Registration:
    with transaction.atomic():
        account = Account.objects.get(pk=account_id)
        _validate_account(account)
        artifact = _resolve_artifact(content, filename, digest)
        target = _find_materialized(artifact.pk, account.pk)
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=_SOURCE_KIND,
            parser_version=PARSER_VERSION,
            status=ImportBatch.Status.PROCESSING,
        )
        if target is not None:
            if target.source_kind == _SOURCE_KIND:
                _finalize_duplicate(batch, target)
            else:
                _finalize_fatal_fields(batch, SOURCE_KIND_CONFLICT, None)
        return _Registration(batch.pk, artifact.pk, account.pk, account.currency, target is not None, batch)


def _resolve_artifact(content: bytes, filename: str, digest: str) -> SourceArtifact:
    artifact = SourceArtifact.objects.filter(content_digest=digest).first()
    if artifact is None:
        try:
            with transaction.atomic():
                artifact = SourceArtifact.objects.create(
                    original_filename=filename,
                    content_digest=digest,
                    content=content,
                )
        except IntegrityError:
            artifact = SourceArtifact.objects.filter(content_digest=digest).first()
            if artifact is None:
                raise
    if bytes(artifact.content) != content:
        raise BciHistoricalImportServiceError("content_digest_collision")
    return artifact


def _find_materialized(artifact_id: UUID, account_id: UUID) -> ImportBatch | None:
    return ImportBatch.objects.filter(
        source_artifact_id=artifact_id,
        account_id=account_id,
        status__in=_MATERIALIZED_STATUSES,
    ).order_by("completed_at", "pk").first()


def _validate_result(result: BciHistoricalParseResult, registration: _Registration, expected_source_account_id: str) -> None:
    metadata = result.metadata
    if (
        result.provider != "BCI"
        or result.product != "current_account"
        or result.source_variant != SOURCE_VARIANT
        or result.parser_version != PARSER_VERSION
        or metadata is None
        or metadata.currency != registration.currency
        or metadata.source_account_id != expected_source_account_id
    ):
        if metadata is not None and metadata.source_account_id != expected_source_account_id:
            raise BciHistoricalImportServiceError(SOURCE_ACCOUNT_MISMATCH)
        raise BciHistoricalImportServiceError(ACCOUNT_CONTEXT_CHANGED)
    if registration.currency != "CLP":
        raise BciHistoricalImportServiceError("account_currency_unsupported")
    if result.parsed_count + result.ignored_count + result.rejected_count != len(result.records):
        raise BciHistoricalImportServiceError("parser_result_invalid")
    if any(record.outcome is BciRowOutcome.PARSED and record.signed_amount is None for record in result.records):
        raise BciHistoricalImportServiceError("parser_result_invalid")


def _materialize(registration: _Registration, result: BciHistoricalParseResult) -> ImportBatch:
    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=registration.account_id)
        _validate_account(account)
        batch = ImportBatch.objects.select_for_update().get(pk=registration.batch_id)
        if batch.status != ImportBatch.Status.PROCESSING:
            raise BciHistoricalImportServiceError("import_attempt_context_changed")
        target = _find_materialized(registration.artifact_id, registration.account_id)
        if target is not None:
            if target.source_kind == _SOURCE_KIND:
                _finalize_duplicate(batch, target)
                return batch
            _finalize_fatal_fields(batch, SOURCE_KIND_CONFLICT, SOURCE_VARIANT)
            return batch
        metadata = result.metadata
        assert metadata is not None
        batch_evidence = BciHistoricalPdfBatchEvidence(
            import_batch=batch,
            statement_id=metadata.statement_id,
            source_account_id=metadata.source_account_id,
            statement_currency=metadata.currency,
            gir_version=result.gir_version,
            extraction_profile_version=result.extraction_profile_version,
            provenance_schema_version=PROVENANCE_SCHEMA_VERSION,
            metadata_provenance=serialize_field_provenance_map(metadata.fields),
            reconciliation_provenance=_reconciliation_provenance(result),
            reconciliation_checks=_reconciliation_checks(result),
            reconciliation_missing_operands=list(result.reconciliation.missing_operands),
            printed_total_debits=metadata.printed_total_debits,
            printed_total_credits=metadata.printed_total_credits,
        )
        batch_evidence.full_clean()
        batch_evidence.save()
        raw_records: dict[int, RawRecord] = {}
        for ordinal, record in enumerate(result.records, 1):
            raw = RawRecord(
                import_batch=batch,
                record_kind=_RECORD_KIND,
                record_ordinal=ordinal,
                parse_outcome=record.outcome.value,
                parser_codes=[record.reason_code],
            )
            raw.full_clean()
            raw.save()
            evidence = BciHistoricalPdfRecordEvidence(
                raw_record=raw,
                page_ordinal=record.page_ordinal,
                source_row_ordinal=record.source_row_ordinal or None,
                line_ordinals=list(record.line_ordinals),
                token_ordinals=list(record.token_ordinals),
                field_provenance=serialize_field_provenance_map(record.fields),
                source_date_text=record.source_date_text,
                accounting_date=record.accounting_date,
                transaction_date=None,
                branch=record.branch,
                description=record.description,
                source_reference=record.reference,
                debit=record.debit,
                credit=record.credit,
                signed_amount=record.signed_amount,
                running_balance=record.running_balance,
                currency=record.currency,
            )
            evidence.full_clean()
            evidence.save()
            raw_records[ordinal] = raw
            if record.outcome is BciRowOutcome.PARSED:
                _create_observation(raw, account, record)
        _finalize_batch(batch, result)
        return batch


def _create_observation(raw: RawRecord, account: Account, record) -> FinancialObservation:
    assert record.accounting_date is not None and record.signed_amount is not None
    key = uuid5(OBSERVATION_NAMESPACE, f"{raw.pk}:{account.pk}:{OBSERVATION_METHOD}:{OBSERVATION_VERSION}")
    existing = FinancialObservation.objects.filter(idempotency_key=key).first()
    if existing is not None:
        if existing.raw_record_id != raw.pk or existing.account_id != account.pk:
            raise BciHistoricalImportServiceError("observation_idempotency_conflict")
        return existing
    observation = FinancialObservation(
        raw_record=raw,
        account=account,
        transaction_date=None,
        accounting_date=record.accounting_date,
        signed_amount=record.signed_amount,
        currency=account.currency,
        description=_optional_text(record.description),
        source_reference=_optional_text(record.reference),
        interpretation_method=OBSERVATION_METHOD,
        interpretation_version=OBSERVATION_VERSION,
        idempotency_key=key,
        state=FinancialObservation.State.UNRESOLVED,
    )
    observation.full_clean()
    observation.save()
    return observation


def _finalize_batch(batch: ImportBatch, result: BciHistoricalParseResult) -> None:
    metadata = result.metadata
    assert metadata is not None
    batch.status = ImportBatch.Status.REJECTED if result.parsed_count == 0 and result.rejected_count else ImportBatch.Status.PARTIAL if result.rejected_count else ImportBatch.Status.ACCEPTED
    batch.source_variant = SOURCE_VARIANT
    batch.completed_at = timezone.now()
    batch.period_start = metadata.period_start
    batch.period_end = metadata.period_end
    batch.parsed_count = result.parsed_count
    batch.ignored_count = result.ignored_count
    batch.rejected_count = result.rejected_count
    batch.reconciliation_status = result.reconciliation.status.value
    batch.opening_balance = metadata.opening_balance
    batch.ending_balance = metadata.closing_balance
    batch.reconciliation_difference = result.reconciliation.difference
    batch.failure_stage = None
    batch.failure_code = None
    batch.full_clean()
    batch.save()


def _reconciliation_provenance(result: BciHistoricalParseResult) -> dict[str, object]:
    fields = {}
    for name, check in result.reconciliation.checks.items():
        fields.update({f"{name}.{field}": value for field, value in check.fields.items()})
    if not fields and result.metadata is not None:
        fields = dict(result.metadata.fields)
    return serialize_field_provenance_map(fields)


def _reconciliation_checks(result: BciHistoricalParseResult) -> dict[str, object]:
    return {
        name: {
            "status": check.status.value,
            "reason_code": check.reason_code,
            "difference": str(check.difference) if check.difference is not None else None,
        }
        for name, check in result.reconciliation.checks.items()
    }


def _record_fatal(batch_id: UUID, code: str, source_variant: str | None) -> ImportBatch:
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status != ImportBatch.Status.PROCESSING:
                raise BciHistoricalImportOperationalError("fatal_compensation_conflict")
            if batch.raw_records.exists() or BciHistoricalPdfBatchEvidence.objects.filter(import_batch=batch).exists() or BciHistoricalPdfRecordEvidence.objects.filter(raw_record__import_batch=batch).exists() or FinancialObservation.objects.filter(raw_record__import_batch=batch).exists():
                raise BciHistoricalImportOperationalError("fatal_compensation_graph_present")
            _finalize_fatal_fields(batch, code, source_variant)
            return batch
    except BciHistoricalImportOperationalError:
        raise
    except Exception:
        raise BciHistoricalImportOperationalError("fatal_compensation_failed") from None


def _finalize_duplicate(batch: ImportBatch, target: ImportBatch) -> None:
    batch.status = ImportBatch.Status.DUPLICATE
    batch.source_variant = target.source_variant
    batch.duplicate_of = target
    batch.completed_at = timezone.now()
    _clear_batch(batch)
    batch.save()


def _finalize_fatal_fields(batch: ImportBatch, code: str, source_variant: str | None) -> None:
    batch.status = ImportBatch.Status.FATAL
    batch.source_variant = source_variant
    batch.completed_at = timezone.now()
    batch.duplicate_of = None
    _clear_batch(batch)
    batch.failure_stage = ImportBatch.FailureStage.BOUNDARY if code in {SOURCE_KIND_CONFLICT, ACCOUNT_CONTEXT_CHANGED, SOURCE_ACCOUNT_MISMATCH} else ImportBatch.FailureStage.PARSER
    batch.failure_code = code
    batch.save()


def _clear_batch(batch: ImportBatch) -> None:
    batch.sheet_alias = None
    batch.worksheet_name = None
    batch.worksheet_ordinal = None
    batch.period_start = None
    batch.period_end = None
    batch.parsed_count = 0
    batch.ignored_count = 0
    batch.rejected_count = 0
    batch.reconciliation_status = None
    batch.opening_balance = None
    batch.ending_balance = None
    batch.reconciliation_difference = None


def _validate_account(account: Account) -> None:
    if account.kind != Account.Kind.CURRENT:
        raise BciHistoricalImportServiceError("account_kind_unsupported")
    if account.economic_orientation != Account.EconomicOrientation.ASSET:
        raise BciHistoricalImportServiceError("account_orientation_unsupported")
    if account.currency != "CLP":
        raise BciHistoricalImportServiceError("account_currency_unsupported")


def _normalize_source_account_id(value: object) -> str:
    if not isinstance(value, str):
        raise BciHistoricalImportServiceError("expected_source_account_invalid")
    value = value.strip()
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise BciHistoricalImportServiceError("expected_source_account_invalid")
    return value


def _normalize_filename(value: object) -> str:
    if not isinstance(value, str):
        raise BciHistoricalImportServiceError("filename_invalid")
    value = unicodedata.normalize("NFC", value).replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not value or value in {".", ".."} or len(value) > 255 or any(unicodedata.category(char) == "Cc" for char in value):
        raise BciHistoricalImportServiceError("filename_invalid")
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
