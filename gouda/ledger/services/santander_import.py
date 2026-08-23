"""Santander current-account import boundary and synchronous application service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
from math import isfinite
import re
import unicodedata
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from gouda.santander_parser import (
    PARSER_VERSION,
    AmbiguousWorksheetError,
    MalformedWorkbookError,
    NormalizedMovement,
    ParseResult,
    ParserError,
    RawRecord as ParserRawRecord,
    ReconciliationResult,
    ReconciliationStatus,
    RowOutcome,
    RowResult,
    SourceCell,
    UnsupportedWorkbookError,
    parse_workbook,
)

from ..models import Account, ImportBatch, Movement, RawRecord, SourceArtifact
from ..validation import validate_exact_money


SANTANDER_SOURCE_VARIANT_V1 = "v1"
SOURCE_VARIANT_UNSUPPORTED = "source_variant_unsupported"
PARSER_RESULT_GRAPH_INVALID = "parser_result_graph_invalid"
PARSER_ERROR_UNRECOGNIZED = "parser_error_unrecognized"
PARSER_UNEXPECTED = "parser_unexpected"
ACCOUNT_CONTEXT_CHANGED = "account_context_changed"
IMPORT_ATTEMPT_CONTEXT_CHANGED = "import_attempt_context_changed"
BOUNDARY_VALIDATION_FAILED = "boundary_validation_failed"
MATERIALIZATION_INTEGRITY_ERROR = "materialization_integrity_error"
MATERIALIZATION_DATABASE_ERROR = "materialization_database_error"
MATERIALIZATION_FAILED = "materialization_failed"

_SOURCE_KIND = SourceArtifact.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX
_MATERIALIZED_STATUSES = (
    ImportBatch.Status.ACCEPTED,
    ImportBatch.Status.PARTIAL,
    ImportBatch.Status.REJECTED,
)
_SAFE_MONEY_CODES = frozenset(
    {
        "money_not_finite",
        "money_scale_exceeded",
        "money_precision_exceeded",
        "movement_amount_zero",
    }
)

_EXPECTED_COLUMNS = tuple("ABCDEFG")
_EXPECTED_COLUMN_SET = frozenset(_EXPECTED_COLUMNS)
_COLUMN_RE = re.compile(r"^[A-Z]+$")

_KNOWN_ROW_CODES = frozenset(
    {
        "amount_invalid",
        "amount_missing",
        "auxiliary_row",
        "blank_row",
        "commission_summary",
        "commission_summary_section",
        "date_invalid",
        "date_outside_period",
        "date_unsupported",
        "date_year_ambiguous",
        "debit_credit_conflict",
        "formula_unsupported",
        "header_row",
        "metadata_row",
        "negative_source_amount",
        "post_summary_section",
        "repeated_header",
        "running_balance_invalid",
        "zero_amount_unsupported",
    }
)
_PARSED_ROW_CODES = frozenset({"running_balance_invalid"})
_IGNORED_ROW_CODES = frozenset(
    {
        "auxiliary_row",
        "blank_row",
        "commission_summary",
        "commission_summary_section",
        "header_row",
        "metadata_row",
        "post_summary_section",
        "repeated_header",
    }
)
_REJECTED_ROW_CODES = _KNOWN_ROW_CODES - _PARSED_ROW_CODES - _IGNORED_ROW_CODES

_HEADER_LABELS = {
    "date": frozenset({"date", "fecha", "fechamovimiento", "fechaoperacion"}),
    "description": frozenset({"description", "descripcion", "detalle", "glosa", "concepto"}),
    "debit": frozenset({"debit", "cargo", "cargos", "debe"}),
    "credit": frozenset({"credit", "abono", "abonos", "haber"}),
    "balance": frozenset({"balance", "saldo"}),
}


class SantanderImportValidationError(ValueError):
    """A safe boundary failure represented only by a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SantanderImportServiceError(Exception):
    """Caller-facing Santander failure containing only a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SantanderImportOperationalError(SantanderImportServiceError):
    """A safe failure raised when no truthful durable batch can be returned."""


@dataclass(frozen=True)
class _Registration:
    batch: ImportBatch
    batch_id: UUID
    artifact_id: UUID
    account_id: UUID
    currency: str
    duplicate: bool


@dataclass(frozen=True)
class _PreparedRow:
    parser_row: RowResult
    raw_cells: dict[str, object]


@dataclass(frozen=True)
class _PreparedImport:
    result: ParseResult
    rows: tuple[_PreparedRow, ...]
    source_variant: str
    final_status: str


def import_santander_current_account_xlsx(
    *,
    content: bytes,
    original_filename: str,
    account: Account,
) -> ImportBatch:
    """Import one Santander current-account XLSX into the canonical ledger."""

    if type(content) is not bytes:
        raise SantanderImportServiceError("content_type_invalid")
    if not isinstance(account, Account) or account.pk is None or account._state.adding:
        raise SantanderImportServiceError("account_not_persisted")
    normalized_filename = _normalize_original_filename(original_filename)
    if transaction.get_connection().in_atomic_block:
        raise SantanderImportServiceError("transaction_context_unsupported")

    try:
        digest = _content_digest(content)
        registration = _register_import_attempt(
            content=content,
            normalized_filename=normalized_filename,
            digest=digest,
            account_id=account.pk,
        )
    except SantanderImportServiceError:
        raise
    except DatabaseError:
        raise SantanderImportOperationalError("registration_database_error") from None
    except Exception:
        raise SantanderImportOperationalError("registration_failed") from None

    if registration.duplicate:
        return registration.batch

    try:
        result = parse_workbook(
            content,
            currency=registration.currency,
            account_ref=str(registration.account_id),
        )
    except ParserError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=map_parser_failure_code(error),
            source_variant=None,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code=PARSER_UNEXPECTED,
            source_variant=None,
        )

    recognized_variant: str | None = None
    try:
        validate_santander_parser_result(
            result,
            expected_account_ref=str(registration.account_id),
            expected_currency=registration.currency,
        )
        recognized_variant = assert_santander_v1_structure(result)
        prepared = _prepare_import(
            result=result,
            source_variant=recognized_variant,
        )
    except SantanderImportValidationError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=recognized_variant,
        )
    except ValidationError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=_safe_validation_error_code(error),
            source_variant=recognized_variant,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=BOUNDARY_VALIDATION_FAILED,
            source_variant=recognized_variant,
        )

    try:
        return _materialize_import(registration=registration, prepared=prepared)
    except SantanderImportValidationError as error:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.BOUNDARY,
            failure_code=error.code,
            source_variant=prepared.source_variant,
        )
    except IntegrityError:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_INTEGRITY_ERROR,
            source_variant=prepared.source_variant,
        )
    except DatabaseError:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_DATABASE_ERROR,
            source_variant=prepared.source_variant,
        )
    except Exception:
        return _record_fatal_attempt(
            batch_id=registration.batch_id,
            failure_stage=ImportBatch.FailureStage.PERSISTENCE,
            failure_code=MATERIALIZATION_FAILED,
            source_variant=prepared.source_variant,
        )


def _normalize_original_filename(original_filename: object) -> str:
    if not isinstance(original_filename, str):
        raise SantanderImportServiceError("filename_invalid")
    try:
        normalized = unicodedata.normalize("NFC", original_filename)
        normalized.encode("utf-8", errors="strict")
    except (TypeError, UnicodeError):
        raise SantanderImportServiceError("filename_invalid") from None
    basename = normalized.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if (
        not basename
        or basename in {".", ".."}
        or len(basename) > 255
        or any(unicodedata.category(char) == "Cc" for char in basename)
    ):
        raise SantanderImportServiceError("filename_invalid")
    return basename


def _content_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_account_for_registration(account_id: UUID) -> Account:
    try:
        return Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        raise SantanderImportServiceError("account_not_found") from None


def _validate_trusted_account(account: Account) -> None:
    if account.kind != Account.Kind.CURRENT:
        raise SantanderImportServiceError("account_kind_unsupported")
    if not isinstance(account.currency, str) or re.fullmatch(r"[A-Z]{3}", account.currency) is None:
        raise SantanderImportServiceError("account_currency_invalid")


def _register_import_attempt(
    *,
    content: bytes,
    normalized_filename: str,
    digest: str,
    account_id: UUID,
) -> _Registration:
    with transaction.atomic():
        account = _load_account_for_registration(account_id)
        _validate_trusted_account(account)
        artifact = _resolve_source_artifact(
            content=content,
            normalized_filename=normalized_filename,
            digest=digest,
        )
        target = _find_materialized_batch(artifact_id=artifact.pk, account_id=account.pk)
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            parser_version=PARSER_VERSION,
            status=ImportBatch.Status.PROCESSING,
        )
        if target is not None:
            _finalize_duplicate(batch=batch, target=target)
        return _Registration(
            batch=batch,
            batch_id=batch.pk,
            artifact_id=artifact.pk,
            account_id=account.pk,
            currency=account.currency,
            duplicate=target is not None,
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
                    source_kind=_SOURCE_KIND,
                    original_filename=normalized_filename,
                    content_digest=digest,
                    content=content,
                )
        except IntegrityError:
            artifact = SourceArtifact.objects.filter(content_digest=digest).first()
            if artifact is None:
                raise

    if bytes(artifact.content) != content:
        raise SantanderImportServiceError("content_digest_collision")
    if artifact.source_kind != _SOURCE_KIND:
        raise SantanderImportServiceError("artifact_source_kind_mismatch")
    return artifact


def _find_materialized_batch(*, artifact_id: UUID, account_id: UUID) -> ImportBatch | None:
    return (
        ImportBatch.objects.filter(
            source_artifact_id=artifact_id,
            account_id=account_id,
            status__in=_MATERIALIZED_STATUSES,
        )
        .order_by("completed_at", "pk")
        .first()
    )


def _finalize_duplicate(*, batch: ImportBatch, target: ImportBatch) -> None:
    batch.status = ImportBatch.Status.DUPLICATE
    batch.source_variant = target.source_variant
    batch.duplicate_of = target
    batch.completed_at = timezone.now()
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
    batch.failure_stage = None
    batch.failure_code = None
    batch.save(
        update_fields=[
            "status",
            "source_variant",
            "duplicate_of",
            "completed_at",
            "sheet_alias",
            "worksheet_name",
            "worksheet_ordinal",
            "period_start",
            "period_end",
            "parsed_count",
            "ignored_count",
            "rejected_count",
            "reconciliation_status",
            "opening_balance",
            "ending_balance",
            "reconciliation_difference",
            "failure_stage",
            "failure_code",
        ]
    )


def _prepare_import(
    *,
    result: ParseResult,
    source_variant: str,
) -> _PreparedImport:
    for movement in result.parsed_movements:
        validate_movement_money(
            signed_amount=movement.signed_amount,
            running_balance=movement.running_balance,
        )
    validate_reconciliation_money(
        opening_balance=result.reconciliation.opening_balance,
        ending_balance=result.reconciliation.ending_balance,
        difference=result.reconciliation.difference,
    )
    rows = tuple(
        _PreparedRow(
            parser_row=row,
            raw_cells=serialize_santander_raw_cells(row.raw_record.raw_cells),
        )
        for row in result.rows
    )
    final_status = derive_batch_status(
        parsed_count=result.parsed_count,
        rejected_count=result.rejected_count,
    )
    return _PreparedImport(
        result=result,
        rows=rows,
        source_variant=source_variant,
        final_status=final_status,
    )


def _safe_validation_error_code(error: ValidationError) -> str:
    code = getattr(error, "code", None)
    return code if code in _SAFE_MONEY_CODES else BOUNDARY_VALIDATION_FAILED


def _materialize_import(*, registration: _Registration, prepared: _PreparedImport) -> ImportBatch:
    with transaction.atomic():
        try:
            account = Account.objects.select_for_update().get(pk=registration.account_id)
        except Account.DoesNotExist:
            raise SantanderImportValidationError(ACCOUNT_CONTEXT_CHANGED) from None
        if account.kind != Account.Kind.CURRENT or account.currency != registration.currency:
            raise SantanderImportValidationError(ACCOUNT_CONTEXT_CHANGED)

        try:
            batch = ImportBatch.objects.select_for_update().get(pk=registration.batch_id)
        except ImportBatch.DoesNotExist:
            raise SantanderImportValidationError(IMPORT_ATTEMPT_CONTEXT_CHANGED) from None
        if (
            batch.status != ImportBatch.Status.PROCESSING
            or batch.source_artifact_id != registration.artifact_id
            or batch.account_id != registration.account_id
            or batch.parser_version != PARSER_VERSION
            or batch.source_variant is not None
        ):
            raise SantanderImportValidationError(IMPORT_ATTEMPT_CONTEXT_CHANGED)

        target = _find_materialized_batch(
            artifact_id=registration.artifact_id,
            account_id=registration.account_id,
        )
        if target is not None:
            _finalize_duplicate(batch=batch, target=target)
            return batch

        raw_records = _create_raw_records(batch=batch, rows=prepared.rows)
        _create_movements(account=account, rows=prepared.rows, raw_records=raw_records)
        _finalize_materialized_batch(batch=batch, prepared=prepared)
        return batch


def _create_raw_records(
    *,
    batch: ImportBatch,
    rows: tuple[_PreparedRow, ...],
) -> dict[str, RawRecord]:
    persisted: dict[str, RawRecord] = {}
    for prepared_row in rows:
        parser_row = prepared_row.parser_row
        raw = RawRecord.objects.create(
            import_batch=batch,
            row_number=parser_row.raw_record.row_number,
            raw_cells=prepared_row.raw_cells,
            row_class=parser_row.raw_record.row_class,
            parse_outcome=parser_row.outcome.value,
            parser_codes=list(parser_row.error_codes),
        )
        persisted[parser_row.raw_record.raw_record_id] = raw
    return persisted


def _create_movements(
    *,
    account: Account,
    rows: tuple[_PreparedRow, ...],
    raw_records: Mapping[str, RawRecord],
) -> None:
    for prepared_row in rows:
        movement = prepared_row.parser_row.movement
        if movement is None:
            continue
        Movement.objects.create(
            raw_record=raw_records[movement.source_record_id],
            account=account,
            occurrence_date=movement.occurrence_date,
            signed_amount=movement.signed_amount,
            currency=account.currency,
            description=movement.description,
            source_reference=movement.source_reference,
            running_balance=movement.running_balance,
            amount_source_column=movement.provenance["source_columns"][1],
        )


def _finalize_materialized_batch(*, batch: ImportBatch, prepared: _PreparedImport) -> None:
    result = prepared.result
    reconciliation = result.reconciliation
    batch.status = prepared.final_status
    batch.source_variant = prepared.source_variant
    batch.completed_at = timezone.now()
    batch.sheet_alias = result.sheet_alias
    batch.worksheet_name = result.worksheet_name
    batch.worksheet_ordinal = result.worksheet_ordinal
    batch.period_start = result.period_start
    batch.period_end = result.period_end
    batch.parsed_count = result.parsed_count
    batch.ignored_count = result.ignored_count
    batch.rejected_count = result.rejected_count
    batch.reconciliation_status = reconciliation.status.value
    batch.opening_balance = reconciliation.opening_balance
    batch.ending_balance = reconciliation.ending_balance
    batch.reconciliation_difference = reconciliation.difference
    batch.failure_stage = None
    batch.failure_code = None
    batch.save(
        update_fields=[
            "status",
            "source_variant",
            "completed_at",
            "sheet_alias",
            "worksheet_name",
            "worksheet_ordinal",
            "period_start",
            "period_end",
            "parsed_count",
            "ignored_count",
            "rejected_count",
            "reconciliation_status",
            "opening_balance",
            "ending_balance",
            "reconciliation_difference",
            "failure_stage",
            "failure_code",
        ]
    )


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
                raise SantanderImportOperationalError("fatal_compensation_conflict")
            batch.status = ImportBatch.Status.FATAL
            batch.source_variant = source_variant
            batch.completed_at = timezone.now()
            batch.duplicate_of = None
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
            batch.failure_stage = failure_stage
            batch.failure_code = failure_code
            batch.save()
            return batch
    except SantanderImportOperationalError:
        raise
    except Exception:
        raise SantanderImportOperationalError("fatal_compensation_failed") from None


def serialize_santander_raw_cells(raw_cells: Mapping[str, SourceCell]) -> dict[str, object]:
    """Serialize one parser row as deterministic, tagged JSON-compatible data."""

    if not isinstance(raw_cells, Mapping):
        raise SantanderImportValidationError("raw_record_serialization_invalid")

    ordered_cells: list[dict[str, object]] = []
    try:
        columns = sorted(raw_cells, key=_column_number)
    except (TypeError, ValueError):
        raise SantanderImportValidationError("raw_record_serialization_invalid") from None

    for column in columns:
        if not isinstance(column, str) or _COLUMN_RE.fullmatch(column) is None:
            raise SantanderImportValidationError("raw_record_serialization_invalid")
        _validate_json_string(column)
        cell = raw_cells[column]
        if not isinstance(cell, SourceCell):
            raise SantanderImportValidationError("raw_record_serialization_invalid")
        if cell.cell_type is not None:
            if not isinstance(cell.cell_type, str):
                raise SantanderImportValidationError("raw_record_serialization_invalid")
            _validate_json_string(cell.cell_type)
        if cell.number_format is not None:
            if not isinstance(cell.number_format, str):
                raise SantanderImportValidationError("raw_record_serialization_invalid")
            _validate_json_string(cell.number_format)
        if not isinstance(cell.is_date, bool) or not isinstance(cell.is_formula, bool):
            raise SantanderImportValidationError("raw_record_serialization_invalid")

        ordered_cells.append(
            {
                "column": column,
                "value": _serialize_cell_value(cell.value),
                "cell_type": cell.cell_type,
                "number_format": cell.number_format,
                "is_date": cell.is_date,
                "is_formula": cell.is_formula,
            }
        )

    return {"schema": "santander-source-row-v1", "cells": ordered_cells}


def derive_batch_status(*, parsed_count: int, rejected_count: int) -> str:
    """Derive the materialized batch status independently of reconciliation."""

    if not _is_nonnegative_int(parsed_count) or not _is_nonnegative_int(rejected_count):
        raise ValueError("row counts must be nonnegative integers")
    if rejected_count == 0:
        return ImportBatch.Status.ACCEPTED
    if parsed_count > 0:
        return ImportBatch.Status.PARTIAL
    return ImportBatch.Status.REJECTED


def map_parser_failure_code(error: BaseException) -> str:
    """Map parser failures through an explicit safe class/code whitelist."""

    known: tuple[tuple[type[ParserError], frozenset[str]], ...] = (
        (MalformedWorkbookError, frozenset({"xlsx_invalid"})),
        (AmbiguousWorksheetError, frozenset({"ambiguous_statement_worksheets"})),
        (
            UnsupportedWorkbookError,
            frozenset(
                {
                    "formula_unsupported",
                    "movement_header_not_found",
                    "period_context_ambiguous",
                    "period_context_invalid",
                    "period_context_missing",
                }
            ),
        ),
    )
    for error_type, codes in known:
        if isinstance(error, error_type):
            return error.code if error.code in codes else PARSER_ERROR_UNRECOGNIZED
    return PARSER_ERROR_UNRECOGNIZED if isinstance(error, ParserError) else PARSER_UNEXPECTED


def validate_movement_money(*, signed_amount: Decimal, running_balance: Decimal | None) -> None:
    """Validate movement money without quantizing or changing parser output."""

    validate_exact_money(signed_amount, field_name="signed_amount")
    if signed_amount == 0:
        raise ValidationError(
            "signed_amount must be nonzero.",
            code="movement_amount_zero",
        )
    if running_balance is not None:
        validate_exact_money(running_balance, field_name="running_balance")


def validate_reconciliation_money(
    *,
    opening_balance: Decimal | None,
    ending_balance: Decimal | None,
    difference: Decimal | None,
) -> None:
    """Validate every persisted reconciliation value through the money domain."""

    for field_name, value in (
        ("opening_balance", opening_balance),
        ("ending_balance", ending_balance),
        ("reconciliation_difference", difference),
    ):
        if value is not None:
            validate_exact_money(value, field_name=field_name)


def validate_santander_parser_result(
    result: ParseResult,
    *,
    expected_account_ref: str,
    expected_currency: str,
    expected_parser_version: str = PARSER_VERSION,
) -> None:
    """Validate the frozen parser's complete result graph before persistence."""

    try:
        _validate_santander_parser_result(
            result,
            expected_account_ref=expected_account_ref,
            expected_currency=expected_currency,
            expected_parser_version=expected_parser_version,
        )
    except SantanderImportValidationError:
        raise
    except Exception:
        raise SantanderImportValidationError(PARSER_RESULT_GRAPH_INVALID) from None


def assert_santander_v1_structure(result: ParseResult) -> str:
    """Assert the supported Santander v1 layout without changing parser behavior."""

    try:
        _assert_santander_v1_structure(result)
    except SantanderImportValidationError:
        raise
    except Exception:
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED) from None
    return SANTANDER_SOURCE_VARIANT_V1


def recognize_santander_v1(
    result: ParseResult,
    *,
    expected_account_ref: str,
    expected_currency: str,
    expected_parser_version: str = PARSER_VERSION,
) -> str:
    """Validate the parser graph and return the internally recognized variant."""

    validate_santander_parser_result(
        result,
        expected_account_ref=expected_account_ref,
        expected_currency=expected_currency,
        expected_parser_version=expected_parser_version,
    )
    return assert_santander_v1_structure(result)


def _serialize_cell_value(value: object | None) -> dict[str, object]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "text": f"{value:d}"}
    if isinstance(value, str):
        _validate_json_string(value)
        return {"type": "string", "text": value}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SantanderImportValidationError("raw_record_serialization_invalid")
        return {"type": "decimal", "text": format(value, "f")}
    if isinstance(value, float):
        if not isfinite(value):
            raise SantanderImportValidationError("raw_record_serialization_invalid")
        return {"type": "float", "hex": value.hex()}
    if isinstance(value, datetime):
        return {"type": "datetime", "text": value.isoformat(timespec="microseconds")}
    if isinstance(value, date):
        return {"type": "date", "text": value.isoformat()}
    raise SantanderImportValidationError("raw_record_serialization_invalid")


def _validate_json_string(value: str) -> None:
    if "\x00" in value:
        raise SantanderImportValidationError("raw_record_serialization_invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise SantanderImportValidationError("raw_record_serialization_invalid") from None


def _column_number(column: object) -> int:
    if not isinstance(column, str) or _COLUMN_RE.fullmatch(column) is None:
        raise ValueError
    result = 0
    for char in column:
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _graph_failure() -> None:
    raise SantanderImportValidationError(PARSER_RESULT_GRAPH_INVALID)


def _validate_santander_parser_result(
    result: ParseResult,
    *,
    expected_account_ref: str,
    expected_currency: str,
    expected_parser_version: str,
) -> None:
    if not isinstance(result, ParseResult):
        _graph_failure()
    if not expected_parser_version or expected_parser_version != PARSER_VERSION:
        _graph_failure()
    if not isinstance(expected_account_ref, str) or not expected_account_ref:
        _graph_failure()
    if not isinstance(expected_currency, str) or not expected_currency:
        _graph_failure()
    if not isinstance(result.sheet_alias, str) or not result.sheet_alias:
        _graph_failure()
    if not isinstance(result.worksheet_name, str) or not result.worksheet_name:
        _graph_failure()
    if not _is_nonnegative_int(result.worksheet_ordinal) or result.worksheet_ordinal == 0:
        _graph_failure()
    if result.sheet_alias != f"S{result.worksheet_ordinal}":
        _graph_failure()
    if type(result.period_start) is not date or type(result.period_end) is not date:
        _graph_failure()
    if result.period_start > result.period_end:
        _graph_failure()
    if not isinstance(result.rows, tuple):
        _graph_failure()

    expected_row_numbers = list(range(1, len(result.rows) + 1))
    actual_row_numbers: list[int] = []
    actual_movements: list[NormalizedMovement] = []
    counts = {outcome: 0 for outcome in RowOutcome}
    record_ids: set[str] = set()

    for row in result.rows:
        if not isinstance(row, RowResult) or not isinstance(row.outcome, RowOutcome):
            _graph_failure()
        if not isinstance(row.raw_record, ParserRawRecord):
            _graph_failure()
        raw = row.raw_record
        if not _is_nonnegative_int(raw.row_number) or raw.row_number == 0:
            _graph_failure()
        actual_row_numbers.append(raw.row_number)
        if raw.raw_record_id in record_ids:
            _graph_failure()
        record_ids.add(raw.raw_record_id)
        if raw.raw_record_id != f"{result.sheet_alias}:row:{raw.row_number}":
            _graph_failure()
        if (
            raw.sheet_alias != result.sheet_alias
            or raw.worksheet_name != result.worksheet_name
            or raw.worksheet_ordinal != result.worksheet_ordinal
        ):
            _graph_failure()
        if raw.row_class not in RawRecord.RowClass.values:
            _graph_failure()
        if not isinstance(raw.raw_cells, Mapping) or not _EXPECTED_COLUMN_SET.issubset(raw.raw_cells):
            _graph_failure()
        for column, cell in raw.raw_cells.items():
            if not isinstance(column, str) or _COLUMN_RE.fullmatch(column) is None:
                _graph_failure()
            if not isinstance(cell, SourceCell):
                _graph_failure()
        if not isinstance(row.error_codes, tuple):
            _graph_failure()
        if any(not isinstance(code, str) or code not in _KNOWN_ROW_CODES for code in row.error_codes):
            _graph_failure()

        counts[row.outcome] += 1
        if row.outcome is RowOutcome.PARSED:
            if raw.row_class != RawRecord.RowClass.MOVEMENT_CANDIDATE:
                _graph_failure()
            if any(code not in _PARSED_ROW_CODES for code in row.error_codes):
                _graph_failure()
            if not isinstance(row.movement, NormalizedMovement):
                _graph_failure()
            _validate_graph_movement(
                row.movement,
                raw,
                result,
                expected_account_ref=expected_account_ref,
                expected_currency=expected_currency,
                expected_parser_version=expected_parser_version,
            )
            actual_movements.append(row.movement)
        else:
            if row.movement is not None or not row.error_codes:
                _graph_failure()
            if row.outcome is RowOutcome.IGNORED:
                if raw.row_class == RawRecord.RowClass.MOVEMENT_CANDIDATE:
                    _graph_failure()
                if any(code not in _IGNORED_ROW_CODES for code in row.error_codes):
                    _graph_failure()
            elif row.outcome is RowOutcome.REJECTED:
                if raw.row_class != RawRecord.RowClass.MOVEMENT_CANDIDATE:
                    _graph_failure()
                if any(code not in _REJECTED_ROW_CODES for code in row.error_codes):
                    _graph_failure()

    if actual_row_numbers != expected_row_numbers:
        _graph_failure()
    if (
        result.parsed_count != counts[RowOutcome.PARSED]
        or result.ignored_count != counts[RowOutcome.IGNORED]
        or result.rejected_count != counts[RowOutcome.REJECTED]
    ):
        _graph_failure()
    if sum(counts.values()) != len(result.rows):
        _graph_failure()
    reported_movements = result.parsed_movements
    if not isinstance(reported_movements, tuple) or len(reported_movements) != len(actual_movements):
        _graph_failure()
    if any(reported is not actual for reported, actual in zip(reported_movements, actual_movements)):
        _graph_failure()

    _validate_reconciliation(result.reconciliation, result.rows, tuple(actual_movements))


def _validate_graph_movement(
    movement: NormalizedMovement,
    raw: ParserRawRecord,
    result: ParseResult,
    *,
    expected_account_ref: str,
    expected_currency: str,
    expected_parser_version: str,
) -> None:
    if movement.source_record_id != raw.raw_record_id:
        _graph_failure()
    if movement.account_ref != expected_account_ref or movement.currency != expected_currency:
        _graph_failure()
    if type(movement.occurrence_date) is not date:
        _graph_failure()
    if not result.period_start <= movement.occurrence_date <= result.period_end:
        _graph_failure()
    if not isinstance(movement.signed_amount, Decimal) or not movement.signed_amount.is_finite():
        _graph_failure()
    if movement.signed_amount == 0:
        _graph_failure()
    if movement.running_balance is not None and (
        not isinstance(movement.running_balance, Decimal) or not movement.running_balance.is_finite()
    ):
        _graph_failure()
    if movement.description is not None and not isinstance(movement.description, str):
        _graph_failure()
    if movement.source_reference is not None and not isinstance(movement.source_reference, str):
        _graph_failure()
    if not isinstance(movement.provenance, Mapping):
        _graph_failure()

    source_columns = ("A", "E") if movement.signed_amount < 0 else ("A", "F")
    if movement.provenance.get("source_columns") != source_columns:
        _graph_failure()
    if (
        movement.provenance.get("sheet_alias") != result.sheet_alias
        or movement.provenance.get("worksheet_name") != result.worksheet_name
        or movement.provenance.get("worksheet_ordinal") != result.worksheet_ordinal
        or movement.provenance.get("row_number") != raw.row_number
        or movement.provenance.get("parser_version") != expected_parser_version
    ):
        _graph_failure()

    amount_column = source_columns[1]
    other_amount_column = "F" if amount_column == "E" else "E"
    if not _cell_present(raw.raw_cells[amount_column]) or _cell_present(raw.raw_cells[other_amount_column]):
        _graph_failure()


def _validate_reconciliation(
    reconciliation: ReconciliationResult,
    rows: tuple[RowResult, ...],
    movements: tuple[NormalizedMovement, ...],
) -> None:
    if not isinstance(reconciliation, ReconciliationResult):
        _graph_failure()
    if not isinstance(reconciliation.status, ReconciliationStatus):
        _graph_failure()
    for value in (reconciliation.opening_balance, reconciliation.ending_balance, reconciliation.difference):
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            _graph_failure()

    rejected_candidates = tuple(
        row
        for row in rows
        if row.raw_record.row_class == RawRecord.RowClass.MOVEMENT_CANDIDATE
        and row.outcome is RowOutcome.REJECTED
    )
    opening = reconciliation.opening_balance
    ending = reconciliation.ending_balance
    difference = reconciliation.difference

    if reconciliation.status in {ReconciliationStatus.RECONCILED, ReconciliationStatus.NOT_RECONCILED}:
        if rejected_candidates or opening is None or ending is None or difference is None:
            _graph_failure()
        recomputed = ending - (opening + sum((movement.signed_amount for movement in movements), Decimal("0")))
        if difference != recomputed:
            _graph_failure()
        if reconciliation.status is ReconciliationStatus.RECONCILED and recomputed != 0:
            _graph_failure()
        if reconciliation.status is ReconciliationStatus.NOT_RECONCILED and recomputed == 0:
            _graph_failure()
    elif reconciliation.status is ReconciliationStatus.INSUFFICIENT_DATA:
        if difference is not None:
            _graph_failure()
        if not movements and not rejected_candidates:
            _graph_failure()
        if not rejected_candidates and opening is not None and ending is not None:
            _graph_failure()
    elif reconciliation.status is ReconciliationStatus.NOT_APPLICABLE:
        if movements or rejected_candidates or difference is not None:
            _graph_failure()
    else:
        _graph_failure()


def _assert_santander_v1_structure(result: ParseResult) -> None:
    if not isinstance(result, ParseResult):
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)

    primary_headers = [row for row in result.rows if "header_row" in row.error_codes]
    if len(primary_headers) != 1 or not _recognized_header(primary_headers[0].raw_record.raw_cells):
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)

    for row in result.rows:
        for column, cell in row.raw_record.raw_cells.items():
            if _column_number(column) > len(_EXPECTED_COLUMNS) and _cell_present(cell):
                raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)

    starts = [index for index, row in enumerate(result.rows) if "commission_summary_section" in row.error_codes]
    ends = [index for index, row in enumerate(result.rows) if "post_summary_section" in row.error_codes]
    marker_starts = [
        index
        for index, row in enumerate(result.rows)
        if _exact_marker(row.raw_record.raw_cells, "C", "resumendecomisiones")
    ]
    marker_ends = [
        index
        for index, row in enumerate(result.rows)
        if _exact_marker(row.raw_record.raw_cells, "A", "mensajes")
    ]
    if marker_starts != starts or marker_ends != ends:
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
    if bool(starts) != bool(ends) or len(starts) > 1 or len(ends) > 1:
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
    if starts:
        start, end = starts[0], ends[0]
        if start >= end:
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
        if not _exact_marker(result.rows[start].raw_record.raw_cells, "C", "resumendecomisiones"):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
        if not _exact_marker(result.rows[end].raw_record.raw_cells, "A", "mensajes"):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
        if any(
            row.outcome is not RowOutcome.IGNORED or "commission_summary" not in row.error_codes
            for row in result.rows[start + 1 : end]
        ):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
        if any("commission_summary" in row.error_codes for row in result.rows[:start] + result.rows[end + 1 :]):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
        if any(
            row.outcome is not RowOutcome.IGNORED or "auxiliary_row" not in row.error_codes
            for row in result.rows[end + 1 :]
        ):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)
    elif any("commission_summary" in row.error_codes for row in result.rows):
        raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)

    header_index = result.rows.index(primary_headers[0])
    for index, row in enumerate(result.rows[header_index + 1 :], header_index + 1):
        if row.raw_record.row_class != RawRecord.RowClass.AUXILIARY or "auxiliary_row" not in row.error_codes:
            continue
        if any(
            later.outcome in {RowOutcome.PARSED, RowOutcome.REJECTED}
            for later in result.rows[index + 1 :]
        ):
            raise SantanderImportValidationError(SOURCE_VARIANT_UNSUPPORTED)


def _recognized_header(cells: Mapping[str, SourceCell]) -> bool:
    labels = {column: _normalize_label(cells[column].value) for column in _EXPECTED_COLUMNS}
    return (
        labels["A"] in _HEADER_LABELS["date"]
        and labels["C"] in _HEADER_LABELS["description"]
        and _header_label_matches(labels["E"], "debit")
        and _header_label_matches(labels["F"], "credit")
        and labels["G"] in _HEADER_LABELS["balance"]
    )


def _header_label_matches(value: str, field_name: str) -> bool:
    if value in _HEADER_LABELS[field_name]:
        return True
    if field_name == "debit":
        return "cargo" in value or "debit" in value
    if field_name == "credit":
        return "abono" in value or "credit" in value
    return False


def _normalize_label(value: object | None) -> str:
    if not isinstance(value, str):
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", ascii_value)


def _exact_marker(cells: Mapping[str, SourceCell], column: str, marker: str) -> bool:
    if _normalize_label(cells[column].value) != marker:
        return False
    return all(not _cell_present(cells[other]) for other in _EXPECTED_COLUMNS if other != column)


def _cell_present(cell: SourceCell) -> bool:
    value = cell.value
    if value is None:
        return False
    return not (isinstance(value, str) and value.strip() == "")
