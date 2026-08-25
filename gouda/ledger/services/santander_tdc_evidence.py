"""Internal persistence projector for synthetic Santander TDC parser results."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Mapping

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from gouda.santander_tdc_pdf.parser import PARSER_VERSION, SOURCE_VARIANT
from gouda.santander_tdc_pdf.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    SantanderTdcProvenanceError,
    serialize_field_provenance_map,
    validate_positive_ordinal_list,
)
from gouda.santander_tdc_pdf.types import (
    FinancialCategory,
    ParserStatus,
    ReconciliationEvidence,
    ReconciliationStatus,
    RowOutcome,
    SectionState,
    SourceRecord,
    StatementMetadata,
    TdcPdfParserResult,
)

from ..models import (
    ImportBatch,
    Movement,
    RawRecord,
    SantanderTdcPdfBatchEvidence,
    SantanderTdcPdfRecordEvidence,
)
from ..validation import validate_exact_money


_SUPPORTED_OPERANDS = {
    "previous_balance",
    "current_billed_balance",
    "purchases_charges",
    "payments_credits",
    "financial_charges",
}


class SantanderTdcEvidenceProjectionError(ValueError):
    """Safe projector-boundary error with no source values."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _materialize_tdc_parser_evidence(
    *,
    import_batch: ImportBatch,
    parser_result: TdcPdfParserResult,
) -> ImportBatch:
    """Project a prepared parser result; never read bytes, parse, or create movements."""

    _validate_projection(import_batch=import_batch, parser_result=parser_result)
    metadata = parser_result.metadata
    assert metadata is not None
    reconciliation = parser_result.reconciliation
    metadata_provenance = serialize_field_provenance_map(metadata.fields)
    reconciliation_provenance = serialize_field_provenance_map(reconciliation.fields)

    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().select_related("account").get(pk=import_batch.pk)
        _validate_projection(import_batch=batch, parser_result=parser_result)

        batch_evidence = SantanderTdcPdfBatchEvidence(
            import_batch=batch,
            provenance_schema_version=PROVENANCE_SCHEMA_VERSION,
            gir_version=parser_result.gir_version,
            extraction_profile_version=parser_result.extraction_profile_version,
            billing_cutoff_date=metadata.billing_cutoff_date,
            payment_due_date=metadata.payment_due_date,
            statement_currency=metadata.statement_currency,
            card_product_context=metadata.card_product_context,
            card_last_four=metadata.card_last_four,
            metadata_provenance=metadata_provenance,
            reconciliation_missing_operands=list(reconciliation.missing_operands),
            reconciliation_provenance=reconciliation_provenance,
            purchases_charges=reconciliation.operands.get("purchases_charges"),
            payments_credits=reconciliation.operands.get("payments_credits"),
            financial_charges=reconciliation.operands.get("financial_charges"),
        )
        batch_evidence.full_clean()
        batch_evidence.save()

        for record_ordinal, record in enumerate(parser_result.records, 1):
            raw_record = RawRecord(
                import_batch=batch,
                record_kind=RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD,
                record_ordinal=record_ordinal,
                row_number=None,
                raw_cells=None,
                row_class=None,
                xlsx_amount_source_column=None,
                parse_outcome=record.outcome.value,
                parser_codes=[record.reason_code],
            )
            raw_record.full_clean()
            raw_record.save()
            evidence = SantanderTdcPdfRecordEvidence(
                raw_record=raw_record,
                page_ordinal=record.page_ordinal,
                section=record.section.value,
                row_group_ordinal=record.row_group_ordinal,
                line_ordinals=list(record.line_ordinals),
                token_ordinals=list(record.token_ordinals),
                field_provenance=serialize_field_provenance_map(record.fields),
                transaction_date=record.transaction_date,
                description_detail=record.description_detail,
                location=record.location,
                reference_authorization=record.reference_authorization,
                billed_currency=record.billed_currency,
                billed_amount=record.billed_amount,
                original_currency=record.original_currency,
                original_amount=record.original_amount,
                section_category=(record.section_category.value if record.section_category else None),
                debt_effect=record.debt_effect,
                installment_number=record.installment_number,
                installment_amount=record.installment_amount,
                header_profile=record.header_profile,
            )
            evidence.full_clean()
            evidence.save()

        if batch.raw_records.count() != len(parser_result.records):
            raise SantanderTdcEvidenceProjectionError("projected_record_count_mismatch")
        if Movement.objects.filter(raw_record__import_batch=batch).exists():
            raise SantanderTdcEvidenceProjectionError("tdc_movement_forbidden")

        batch.status = _batch_status(parser_result)
        batch.source_variant = parser_result.source_variant
        batch.completed_at = timezone.now()
        batch.period_start = metadata.statement_period_start
        batch.period_end = metadata.statement_period_end
        batch.parsed_count = parser_result.parsed_count
        batch.ignored_count = parser_result.ignored_count
        batch.rejected_count = parser_result.rejected_count
        batch.reconciliation_status = reconciliation.status.value
        batch.opening_balance = reconciliation.operands.get("previous_balance")
        batch.ending_balance = reconciliation.operands.get("current_billed_balance")
        batch.reconciliation_difference = reconciliation.difference
        batch.failure_stage = None
        batch.failure_code = None
        batch.full_clean()
        batch.save()
        return batch


def _validate_projection(
    *,
    import_batch: ImportBatch,
    parser_result: TdcPdfParserResult,
) -> None:
    try:
        if not isinstance(import_batch, ImportBatch) or import_batch.pk is None:
            _fail("tdc_batch_invalid")
        if import_batch.status != ImportBatch.Status.PROCESSING:
            _fail("tdc_batch_not_processing")
        if import_batch.source_kind != ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF:
            _fail("tdc_batch_source_kind_invalid")
        if import_batch.parser_version != PARSER_VERSION:
            _fail("tdc_batch_parser_version_invalid")
        if (
            import_batch.account.kind != import_batch.account.Kind.CREDIT_CARD
            or import_batch.account.economic_orientation
            != import_batch.account.EconomicOrientation.LIABILITY
            or re.fullmatch(r"[A-Z]{3}", import_batch.account.currency or "") is None
        ):
            _fail("tdc_batch_account_context_invalid")
        if any((import_batch.sheet_alias, import_batch.worksheet_name, import_batch.worksheet_ordinal)):
            _fail("tdc_batch_spreadsheet_fields_invalid")
        if import_batch.raw_records.exists() or hasattr(import_batch, "santander_tdc_pdf_evidence"):
            _fail("tdc_batch_already_projected")

        if not isinstance(parser_result, TdcPdfParserResult):
            _fail("tdc_parser_result_invalid")
        if (
            parser_result.status is not ParserStatus.RECOGNIZED
            or parser_result.provider != "Santander"
            or parser_result.product != "credit_card"
            or parser_result.parser_version != PARSER_VERSION
            or parser_result.source_variant != SOURCE_VARIANT
            or not parser_result.gir_version
            or not parser_result.extraction_profile_version
            or not isinstance(parser_result.metadata, StatementMetadata)
            or not isinstance(parser_result.reconciliation, ReconciliationEvidence)
            or not isinstance(parser_result.records, tuple)
        ):
            _fail("tdc_parser_result_invalid")
        if parser_result.errors:
            _fail("tdc_parser_result_invalid")
        _validate_metadata(parser_result.metadata)
        if (
            parser_result.metadata.statement_currency is not None
            and parser_result.metadata.statement_currency != import_batch.account.currency
        ):
            _fail("tdc_statement_currency_mismatch")
        _validate_reconciliation(parser_result.reconciliation)
        for record in parser_result.records:
            _validate_record(record, account_currency=import_batch.account.currency)
        if (
            parser_result.parsed_count
            + parser_result.ignored_count
            + parser_result.rejected_count
            != len(parser_result.records)
        ):
            _fail("tdc_parser_record_count_invalid")
    except SantanderTdcEvidenceProjectionError:
        raise
    except (AttributeError, TypeError, ValueError, ValidationError, SantanderTdcProvenanceError):
        raise SantanderTdcEvidenceProjectionError("tdc_parser_result_invalid") from None


def _validate_metadata(metadata: StatementMetadata) -> None:
    if (
        type(metadata.statement_period_start) is not date
        or type(metadata.statement_period_end) is not date
        or type(metadata.billing_cutoff_date) is not date
        or type(metadata.payment_due_date) is not date
        or metadata.statement_period_start > metadata.statement_period_end
        or metadata.card_product_context != "credit_card"
        or re.fullmatch(r"[0-9]{4}", metadata.card_last_four) is None
    ):
        _fail("tdc_metadata_invalid")
    _optional_currency(metadata.statement_currency)
    serialize_field_provenance_map(metadata.fields)
    required_fields = {
        "statement_period",
        "billing_cutoff_date",
        "payment_due_date",
        "card_product_context",
        "card_last_four",
    }
    if metadata.statement_currency is not None:
        required_fields.add("statement_currency")
    if not required_fields <= set(metadata.fields):
        _fail("tdc_metadata_provenance_incomplete")


def _validate_reconciliation(reconciliation: ReconciliationEvidence) -> None:
    if not isinstance(reconciliation.status, ReconciliationStatus):
        _fail("tdc_reconciliation_invalid")
    if not isinstance(reconciliation.operands, Mapping) or set(reconciliation.operands) - _SUPPORTED_OPERANDS:
        _fail("tdc_reconciliation_invalid")
    for name, value in reconciliation.operands.items():
        validate_exact_money(value, field_name=name)
    if reconciliation.difference is not None:
        validate_exact_money(reconciliation.difference, field_name="reconciliation_difference")
    if (
        not isinstance(reconciliation.missing_operands, tuple)
        or any(item not in _SUPPORTED_OPERANDS for item in reconciliation.missing_operands)
        or len(set(reconciliation.missing_operands)) != len(reconciliation.missing_operands)
    ):
        _fail("tdc_reconciliation_invalid")
    serialize_field_provenance_map(reconciliation.fields)
    if not set(reconciliation.operands) <= set(reconciliation.fields):
        _fail("tdc_reconciliation_provenance_incomplete")


def _validate_record(record: SourceRecord, *, account_currency: str) -> None:
    if (
        not isinstance(record, SourceRecord)
        or not isinstance(record.outcome, RowOutcome)
        or not isinstance(record.section, SectionState)
        or type(record.page_ordinal) is not int
        or record.page_ordinal <= 0
        or type(record.row_group_ordinal) is not int
        or record.row_group_ordinal < 0
        or not isinstance(record.reason_code, str)
        or not record.reason_code
    ):
        _fail("tdc_record_invalid")
    validate_positive_ordinal_list(list(record.line_ordinals))
    validate_positive_ordinal_list(list(record.token_ordinals))
    serialize_field_provenance_map(record.fields)
    if "row" not in record.fields:
        _fail("tdc_record_provenance_incomplete")
    if record.transaction_date is not None and type(record.transaction_date) is not date:
        _fail("tdc_record_invalid")
    for value in (
        record.description_detail,
        record.location,
        record.reference_authorization,
        record.header_profile,
    ):
        if value is not None and not isinstance(value, str):
            _fail("tdc_record_invalid")
    _optional_currency(record.billed_currency)
    _optional_currency(record.original_currency)
    if (record.original_amount is None) != (record.original_currency is None):
        _fail("tdc_original_pair_invalid")
    for name in ("billed_amount", "original_amount", "debt_effect", "installment_amount"):
        value = getattr(record, name)
        if value is not None:
            validate_exact_money(value, field_name=name)
    if record.installment_number is not None and (
        type(record.installment_number) is not int or record.installment_number <= 0
    ):
        _fail("tdc_record_invalid")
    if record.section_category is not None and not isinstance(record.section_category, FinancialCategory):
        _fail("tdc_record_invalid")
    field_for_value = {
        "transaction_date": record.transaction_date,
        "description_detail": record.description_detail,
        "location": record.location,
        "reference_authorization": record.reference_authorization,
        "billed_currency": record.billed_currency,
        "billed_amount": record.billed_amount,
        "original_currency": record.original_currency,
        "original_amount": record.original_amount,
        "section_category": record.section_category,
        "installment_number": record.installment_number,
        "installment_amount": record.installment_amount,
        "header_profile": record.header_profile,
    }
    if any(value is not None and name not in record.fields for name, value in field_for_value.items()):
        _fail("tdc_record_provenance_incomplete")
    if record.outcome is RowOutcome.PARSED:
        if (
            record.transaction_date is None
            or record.billed_currency != account_currency
            or record.billed_amount is None
            or record.billed_amount <= 0
            or record.section_category is None
            or record.debt_effect is None
            or not record.header_profile
        ):
            _fail("tdc_parsed_record_invalid")
        expected_debt_effect = (
            -record.billed_amount
            if record.section_category
            in {FinancialCategory.PAYMENT, FinancialCategory.CREDIT_REFUND}
            else record.billed_amount
        )
        if record.debt_effect != expected_debt_effect:
            _fail("tdc_debt_effect_invalid")


def _optional_currency(value: object) -> None:
    if value is not None and (not isinstance(value, str) or re.fullmatch(r"[A-Z]{3}", value) is None):
        _fail("tdc_currency_invalid")


def _batch_status(result: TdcPdfParserResult) -> str:
    if result.rejected_count == 0:
        return ImportBatch.Status.ACCEPTED
    if result.parsed_count:
        return ImportBatch.Status.PARTIAL
    return ImportBatch.Status.REJECTED


def _fail(code: str) -> None:
    raise SantanderTdcEvidenceProjectionError(code)
