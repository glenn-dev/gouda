"""Synchronous Santander TDC PDF import application service."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata
from uuid import UUID

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from gouda.santander_tdc_pdf.extraction import ConformanceCode, ExtractionError
from gouda.santander_tdc_pdf.parser import (
    PARSER_VERSION,
    SOURCE_VARIANT,
    ContradictoryTdcPdfError,
    TdcPdfParserError,
    UnsupportedTdcPdfError,
    parse_tdc_pdf,
)
from gouda.santander_tdc_pdf.types import ParserStatus, RowOutcome, TdcPdfParserResult

from ..models import (
    Account,
    ImportBatch,
    Movement,
    RawRecord,
    SantanderTdcAccountBinding,
    SantanderTdcPdfBatchEvidence,
    SantanderTdcPdfRecordEvidence,
    SourceArtifact,
)
from ..validation import validate_exact_money
from .santander_tdc_evidence import (
    SantanderTdcEvidenceProjectionError,
    _PreparedTdcProjection,
    _finalize_prepared_tdc_batch,
    _persist_prepared_tdc_evidence,
    _prepare_tdc_parser_projection,
)


SOURCE_KIND_CONFLICT = "source_kind_conflict"
CARD_BINDING_MISMATCH = "card_binding_mismatch"
ACCOUNT_CONTEXT_CHANGED = "account_context_changed"
ACCOUNT_BINDING_CONTEXT_CHANGED = "account_binding_context_changed"
IMPORT_ATTEMPT_CONTEXT_CHANGED = "import_attempt_context_changed"
TDC_PARSER_ERROR_UNRECOGNIZED = "tdc_parser_error_unrecognized"
TDC_PARSER_FATAL = "tdc_parser_fatal"
TDC_PARSER_UNEXPECTED = "tdc_parser_unexpected"
MATERIALIZATION_INTEGRITY_ERROR = "materialization_integrity_error"
MATERIALIZATION_DATABASE_ERROR = "materialization_database_error"
MATERIALIZATION_FAILED = "materialization_failed"

_SOURCE_KIND = ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF
_MATERIALIZED_STATUSES = (
    ImportBatch.Status.ACCEPTED,
    ImportBatch.Status.PARTIAL,
    ImportBatch.Status.REJECTED,
)
_SAFE_EXTRACTION_CODES = frozenset(code.value for code in ConformanceCode)
_SAFE_UNSUPPORTED_CODES = frozenset(
    {
        "billed_section_not_found",
        "card_identity_missing",
        "cutoff_date_ambiguous",
        "cutoff_metadata_missing",
        "due_date_ambiguous",
        "due_date_metadata_missing",
        "provider_product_context_missing",
        "statement_context_missing",
        "statement_currency_ambiguous",
        "statement_period_missing",
        "transaction_header_missing",
        "unsupported_gir_profile",
    }
)
_SAFE_CONTRADICTORY_CODES = frozenset(
    {
        "card_identity_conflict",
        "contradictory_section_transition",
        "financial_content_outside_recognized_state",
        "financial_header_outside_recognized_state",
        "header_profile_state_mismatch",
        "incompatible_repeated_header",
        "transaction_header_missing",
        "transaction_header_missing_on_page",
        "unknown_heading_interrupts_financial_structure",
        "unproven_cross_page_continuation",
        "unsupported_column_order",
        "unsupported_financial_table_geometry",
    }
)
_SAFE_PARSER_CODES = _SAFE_UNSUPPORTED_CODES | _SAFE_CONTRADICTORY_CODES


class SantanderTdcImportValidationError(ValueError):
    """Safe internal TDC boundary failure represented only by a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SantanderTdcImportServiceError(Exception):
    """Caller-facing TDC import failure containing only a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SantanderTdcImportOperationalError(SantanderTdcImportServiceError):
    """Raised when no truthful durable batch can be returned."""


@dataclass(frozen=True)
class _Registration:
    batch: ImportBatch
    batch_id: UUID
    artifact_id: UUID
    account_id: UUID
    binding_id: int
    card_last_four: str = field(repr=False)
    currency: str = field(repr=False)
    terminal: bool


def configure_santander_tdc_account_binding(
    *,
    account: Account,
    card_last_four: str,
) -> SantanderTdcAccountBinding:
    """Create an explicit trusted suffix binding without inferring from source."""

    _validate_persisted_account_argument(account)
    _validate_card_last_four(card_last_four)
    if transaction.get_connection().in_atomic_block:
        raise SantanderTdcImportServiceError("transaction_context_unsupported")
    try:
        with transaction.atomic():
            locked_account = _lock_account(account.pk)
            _validate_trusted_account(locked_account)
            binding = (
                SantanderTdcAccountBinding.objects.select_for_update()
                .filter(account=locked_account)
                .first()
            )
            if binding is not None:
                if binding.card_last_four != card_last_four:
                    raise SantanderTdcImportServiceError("account_binding_conflict")
                return binding
            binding = SantanderTdcAccountBinding(
                account=locked_account,
                card_last_four=card_last_four,
            )
            binding.full_clean()
            binding.save()
            return binding
    except SantanderTdcImportServiceError:
        raise
    except DatabaseError:
        raise SantanderTdcImportOperationalError(
            "binding_database_error"
        ) from None
    except Exception:
        raise SantanderTdcImportOperationalError("binding_failed") from None


def import_santander_credit_card_pdf(
    *,
    content: bytes,
    original_filename: str,
    account: Account,
) -> ImportBatch:
    """Import one Santander credit-card PDF into the canonical ledger."""

    if type(content) is not bytes:
        raise SantanderTdcImportServiceError("content_type_invalid")
    if not content:
        raise SantanderTdcImportServiceError("content_empty")
    _validate_persisted_account_argument(account)
    normalized_filename = _normalize_original_filename(original_filename)
    if transaction.get_connection().in_atomic_block:
        raise SantanderTdcImportServiceError("transaction_context_unsupported")
    digest = hashlib.sha256(content).hexdigest()

    try:
        registration = _register_import_attempt(
            content=content,
            normalized_filename=normalized_filename,
            digest=digest,
            account_id=account.pk,
        )
    except SantanderTdcImportServiceError:
        raise
    except DatabaseError:
        raise SantanderTdcImportOperationalError(
            "registration_database_error"
        ) from None
    except Exception:
        raise SantanderTdcImportOperationalError("registration_failed") from None

    if registration.terminal:
        return registration.batch

    try:
        result = parse_tdc_pdf(content)
    except ExtractionError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=_map_extraction_failure_code(error),
            source_variant=None,
        )
    except TdcPdfParserError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=_map_parser_failure_code(error),
            source_variant=None,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=TDC_PARSER_UNEXPECTED,
            source_variant=None,
        )

    if isinstance(result, TdcPdfParserResult) and result.status is ParserStatus.FATAL:
        supported_fatal_identity = _supported_fatal_result_identity(result)
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=_map_fatal_result_code(result),
            source_variant=(SOURCE_VARIANT if supported_fatal_identity else None),
        )

    recognized_variant = (
        SOURCE_VARIANT
        if isinstance(result, TdcPdfParserResult)
        and result.source_variant == SOURCE_VARIANT
        else None
    )
    try:
        prepared = _prepare_tdc_parser_projection(
            import_batch=registration.batch,
            parser_result=result,
        )
        if prepared.card_last_four != registration.card_last_four:
            raise SantanderTdcImportValidationError(CARD_BINDING_MISMATCH)
    except SantanderTdcImportValidationError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=recognized_variant,
        )
    except SantanderTdcEvidenceProjectionError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=recognized_variant,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code="tdc_boundary_validation_failed",
            source_variant=recognized_variant,
        )

    try:
        return _materialize_import(registration=registration, prepared=prepared)
    except SantanderTdcImportValidationError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=SOURCE_VARIANT,
        )
    except SantanderTdcEvidenceProjectionError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=SOURCE_VARIANT,
        )
    except IntegrityError:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_INTEGRITY_ERROR,
            source_variant=SOURCE_VARIANT,
        )
    except DatabaseError:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_DATABASE_ERROR,
            source_variant=SOURCE_VARIANT,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_FAILED,
            source_variant=SOURCE_VARIANT,
        )


def _validate_persisted_account_argument(account: object) -> None:
    if (
        not isinstance(account, Account)
        or account.pk is None
        or account._state.adding
    ):
        raise SantanderTdcImportServiceError("account_not_persisted")


def _validate_card_last_four(card_last_four: object) -> None:
    if (
        not isinstance(card_last_four, str)
        or re.fullmatch(r"[0-9]{4}", card_last_four) is None
    ):
        raise SantanderTdcImportServiceError("card_last_four_invalid")


def _normalize_original_filename(original_filename: object) -> str:
    if not isinstance(original_filename, str):
        raise SantanderTdcImportServiceError("filename_invalid")
    try:
        normalized = unicodedata.normalize("NFC", original_filename)
        normalized.encode("utf-8", errors="strict")
    except (TypeError, UnicodeError):
        raise SantanderTdcImportServiceError("filename_invalid") from None
    basename = normalized.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if (
        not basename
        or basename in {".", ".."}
        or len(basename) > 255
        or any(unicodedata.category(char) == "Cc" for char in basename)
    ):
        raise SantanderTdcImportServiceError("filename_invalid")
    return basename


def _load_account(account_id: UUID) -> Account:
    try:
        return Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        raise SantanderTdcImportServiceError("account_not_found") from None


def _lock_account(account_id: UUID) -> Account:
    try:
        return Account.objects.select_for_update().get(pk=account_id)
    except Account.DoesNotExist:
        raise SantanderTdcImportServiceError("account_not_found") from None


def _validate_trusted_account(account: Account) -> None:
    if account.kind != Account.Kind.CREDIT_CARD:
        raise SantanderTdcImportServiceError("account_kind_unsupported")
    if account.economic_orientation != Account.EconomicOrientation.LIABILITY:
        raise SantanderTdcImportServiceError("account_orientation_unsupported")
    if (
        not isinstance(account.currency, str)
        or re.fullmatch(r"[A-Z]{3}", account.currency) is None
    ):
        raise SantanderTdcImportServiceError("account_currency_invalid")


def _load_binding(account: Account) -> SantanderTdcAccountBinding:
    try:
        return account.santander_tdc_binding
    except SantanderTdcAccountBinding.DoesNotExist:
        raise SantanderTdcImportServiceError("account_binding_missing") from None


def _register_import_attempt(
    *,
    content: bytes,
    normalized_filename: str,
    digest: str,
    account_id: UUID,
) -> _Registration:
    with transaction.atomic():
        account = _load_account(account_id)
        _validate_trusted_account(account)
        binding = _load_binding(account)
        artifact = _resolve_source_artifact(
            content=content,
            normalized_filename=normalized_filename,
            digest=digest,
        )
        target = _find_materialized_batch(
            artifact_id=artifact.pk,
            account_id=account.pk,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=_SOURCE_KIND,
            parser_version=PARSER_VERSION,
            status=ImportBatch.Status.PROCESSING,
        )
        if target is not None:
            if target.source_kind == _SOURCE_KIND:
                _finalize_duplicate(batch=batch, target=target)
            else:
                _finalize_source_kind_conflict(batch=batch, source_variant=None)
        return _Registration(
            batch=batch,
            batch_id=batch.pk,
            artifact_id=artifact.pk,
            account_id=account.pk,
            binding_id=binding.pk,
            card_last_four=binding.card_last_four,
            currency=account.currency,
            terminal=target is not None,
        )


def _resolve_source_artifact(
    *,
    content: bytes,
    normalized_filename: str,
    digest: str,
) -> SourceArtifact:
    artifact = SourceArtifact.objects.filter(content_digest=digest).first()
    if artifact is None:
        try:
            with transaction.atomic():
                artifact = SourceArtifact.objects.create(
                    original_filename=normalized_filename,
                    content_digest=digest,
                    content=content,
                )
        except IntegrityError:
            artifact = SourceArtifact.objects.filter(content_digest=digest).first()
            if artifact is None:
                raise
    if bytes(artifact.content) != content:
        raise SantanderTdcImportServiceError("content_digest_collision")
    return artifact


def _find_materialized_batch(
    *,
    artifact_id: UUID,
    account_id: UUID,
) -> ImportBatch | None:
    return (
        ImportBatch.objects.filter(
            source_artifact_id=artifact_id,
            account_id=account_id,
            status__in=_MATERIALIZED_STATUSES,
        )
        .order_by("completed_at", "pk")
        .first()
    )


def _materialize_import(
    *,
    registration: _Registration,
    prepared: _PreparedTdcProjection,
) -> ImportBatch:
    with transaction.atomic():
        try:
            account = Account.objects.select_for_update().get(
                pk=registration.account_id
            )
        except Account.DoesNotExist:
            raise SantanderTdcImportValidationError(
                ACCOUNT_CONTEXT_CHANGED
            ) from None
        if (
            account.kind != Account.Kind.CREDIT_CARD
            or account.economic_orientation
            != Account.EconomicOrientation.LIABILITY
            or account.currency != registration.currency
        ):
            raise SantanderTdcImportValidationError(ACCOUNT_CONTEXT_CHANGED)

        binding = (
            SantanderTdcAccountBinding.objects.select_for_update()
            .filter(account=account)
            .first()
        )
        if binding is None or binding.pk != registration.binding_id:
            raise SantanderTdcImportValidationError(
                ACCOUNT_BINDING_CONTEXT_CHANGED
            )
        if (
            binding.card_last_four != registration.card_last_four
            or binding.card_last_four != prepared.card_last_four
        ):
            raise SantanderTdcImportValidationError(CARD_BINDING_MISMATCH)

        try:
            batch = ImportBatch.objects.select_for_update().get(
                pk=registration.batch_id
            )
        except ImportBatch.DoesNotExist:
            raise SantanderTdcImportValidationError(
                IMPORT_ATTEMPT_CONTEXT_CHANGED
            ) from None
        if (
            batch.status != ImportBatch.Status.PROCESSING
            or batch.source_artifact_id != registration.artifact_id
            or batch.account_id != registration.account_id
            or batch.source_kind != _SOURCE_KIND
            or batch.parser_version != PARSER_VERSION
            or batch.source_variant is not None
        ):
            raise SantanderTdcImportValidationError(
                IMPORT_ATTEMPT_CONTEXT_CHANGED
            )

        target = _find_materialized_batch(
            artifact_id=registration.artifact_id,
            account_id=registration.account_id,
        )
        if target is not None:
            if target.source_kind == _SOURCE_KIND:
                _finalize_duplicate(batch=batch, target=target)
            else:
                _finalize_source_kind_conflict(
                    batch=batch,
                    source_variant=SOURCE_VARIANT,
                )
            return batch

        raw_records = _persist_prepared_tdc_evidence(
            import_batch=batch,
            prepared=prepared,
        )
        _create_movements(
            account=account,
            prepared=prepared,
            raw_records=raw_records,
        )
        expected_movements = prepared.parser_result.parsed_count
        actual_movements = Movement.objects.filter(
            raw_record__import_batch=batch
        ).count()
        if actual_movements != expected_movements:
            raise SantanderTdcImportValidationError(
                "projected_movement_count_mismatch"
            )
        _finalize_prepared_tdc_batch(import_batch=batch, prepared=prepared)
        return batch


def _create_movements(
    *,
    account: Account,
    prepared: _PreparedTdcProjection,
    raw_records: dict[int, RawRecord],
) -> None:
    for prepared_record in prepared.records:
        record = prepared_record.source_record
        if record.outcome is not RowOutcome.PARSED:
            continue
        assert record.transaction_date is not None
        assert record.debt_effect is not None
        assert record.billed_currency is not None
        signed_amount = -record.debt_effect
        validate_exact_money(signed_amount, field_name="signed_amount")
        if signed_amount == 0:
            raise SantanderTdcImportValidationError(
                "tdc_movement_amount_zero"
            )
        movement = Movement(
            raw_record=raw_records[prepared_record.ordinal],
            account=account,
            occurrence_date=record.transaction_date,
            signed_amount=signed_amount,
            currency=record.billed_currency,
            description=record.description_detail,
            source_reference=record.reference_authorization,
            running_balance=None,
        )
        movement.full_clean()
        movement.save()


def _finalize_duplicate(*, batch: ImportBatch, target: ImportBatch) -> None:
    batch.status = ImportBatch.Status.DUPLICATE
    batch.source_variant = target.source_variant
    batch.duplicate_of = target
    batch.completed_at = timezone.now()
    _clear_non_attempt_fields(batch)
    batch.failure_stage = None
    batch.failure_code = None
    batch.save()


def _finalize_source_kind_conflict(
    *,
    batch: ImportBatch,
    source_variant: str | None,
) -> None:
    batch.status = ImportBatch.Status.FATAL
    batch.source_variant = source_variant
    batch.duplicate_of = None
    batch.completed_at = timezone.now()
    _clear_non_attempt_fields(batch)
    batch.failure_stage = ImportBatch.FailureStage.BOUNDARY
    batch.failure_code = SOURCE_KIND_CONFLICT
    batch.save()


def _clear_non_attempt_fields(batch: ImportBatch) -> None:
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


def _record_fatal_attempt(
    *,
    batch_id: UUID,
    failure_stage: str,
    failure_code: str,
    source_variant: str | None,
) -> ImportBatch:
    try:
        with transaction.atomic():
            batch = ImportBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status != ImportBatch.Status.PROCESSING:
                raise SantanderTdcImportOperationalError(
                    "fatal_compensation_conflict"
                )
            if (
                batch.raw_records.exists()
                or SantanderTdcPdfBatchEvidence.objects.filter(
                    import_batch=batch
                ).exists()
                or SantanderTdcPdfRecordEvidence.objects.filter(
                    raw_record__import_batch=batch
                ).exists()
                or Movement.objects.filter(raw_record__import_batch=batch).exists()
            ):
                raise SantanderTdcImportOperationalError(
                    "fatal_compensation_graph_present"
                )
            batch.status = ImportBatch.Status.FATAL
            batch.source_variant = source_variant
            batch.completed_at = timezone.now()
            batch.duplicate_of = None
            _clear_non_attempt_fields(batch)
            batch.failure_stage = failure_stage
            batch.failure_code = failure_code
            batch.save()
            return batch
    except SantanderTdcImportOperationalError:
        raise
    except Exception:
        raise SantanderTdcImportOperationalError(
            "fatal_compensation_failed"
        ) from None


def _map_extraction_failure_code(error: ExtractionError) -> str:
    code = getattr(error.code, "value", None)
    return code if code in _SAFE_EXTRACTION_CODES else TDC_PARSER_ERROR_UNRECOGNIZED


def _map_parser_failure_code(error: TdcPdfParserError) -> str:
    if isinstance(error, UnsupportedTdcPdfError):
        return (
            error.code
            if error.code in _SAFE_UNSUPPORTED_CODES
            else TDC_PARSER_ERROR_UNRECOGNIZED
        )
    if isinstance(error, ContradictoryTdcPdfError):
        return (
            error.code
            if error.code in _SAFE_CONTRADICTORY_CODES
            else TDC_PARSER_ERROR_UNRECOGNIZED
        )
    return TDC_PARSER_ERROR_UNRECOGNIZED


def _map_fatal_result_code(result: TdcPdfParserResult) -> str:
    if (
        _supported_fatal_result_identity(result)
        and len(result.errors) == 1
        and result.errors[0] in _SAFE_PARSER_CODES
    ):
        return result.errors[0]
    return TDC_PARSER_FATAL


def _supported_fatal_result_identity(result: TdcPdfParserResult) -> bool:
    return (
        result.provider == "Santander"
        and result.product == "credit_card"
        and result.source_variant == SOURCE_VARIANT
        and result.parser_version == PARSER_VERSION
    )
