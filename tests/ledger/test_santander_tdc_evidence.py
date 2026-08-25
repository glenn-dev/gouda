from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
import hashlib
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from gouda.ledger.models import (
    Account,
    ImportBatch,
    Movement,
    RawRecord,
    SantanderTdcPdfBatchEvidence,
    SantanderTdcPdfRecordEvidence,
    SourceArtifact,
)
from gouda.ledger.services.santander_tdc_evidence import (
    SantanderTdcEvidenceProjectionError,
    _materialize_tdc_parser_evidence,
)
from gouda.santander_tdc_pdf.extraction import BoundingBox, GIR_VERSION, PROFILE_VERSION
from gouda.santander_tdc_pdf.parser import PARSER_VERSION, SOURCE_VARIANT
from gouda.santander_tdc_pdf.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    SantanderTdcProvenanceError,
    serialize_field_provenance_map,
    validate_field_provenance_payload,
)
from gouda.santander_tdc_pdf.types import (
    AdditionalPageSpan,
    FieldProvenance,
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


def provenance(role: str, *, page: int = 1, multipage: bool = False) -> FieldProvenance:
    additional = ()
    if multipage:
        additional = (
            AdditionalPageSpan(
                page_ordinal=page + 1,
                line_ordinals=(1,),
                token_ordinals=(20,),
                bbox=BoundingBox(Decimal("10.00"), Decimal("20.00"), Decimal("40.00"), Decimal("30.00")),
                page_width=Decimal("612.00"),
                page_height=Decimal("792.00"),
                normalized_bbox=(Decimal("0.016"), Decimal("0.025"), Decimal("0.065"), Decimal("0.038")),
            ),
        )
    return FieldProvenance(
        page_ordinal=page,
        line_ordinals=(2, 3),
        token_ordinals=(10, 11),
        bbox=BoundingBox(Decimal("12.30"), Decimal("24.50"), Decimal("120.75"), Decimal("36.90")),
        role=role,
        band_relation="inside",
        additional_page_spans=additional,
        page_width=Decimal("612.00"),
        page_height=Decimal("792.00"),
        normalized_bbox=(Decimal("0.020"), Decimal("0.031"), Decimal("0.197"), Decimal("0.047")),
    )


def fields(*names: str, multipage_name: str | None = None) -> dict[str, FieldProvenance]:
    return {
        name: provenance(name, multipage=name == multipage_name)
        for name in names
    }


def synthetic_result() -> TdcPdfParserResult:
    metadata = StatementMetadata(
        statement_period_start=date(2026, 6, 1),
        statement_period_end=date(2026, 6, 30),
        billing_cutoff_date=date(2026, 6, 30),
        payment_due_date=date(2026, 7, 10),
        card_product_context="credit_card",
        card_last_four="0079",
        statement_currency="CLP",
        fields=fields(
            "statement_period",
            "billing_cutoff_date",
            "payment_due_date",
            "card_product_context",
            "card_last_four",
            "statement_currency",
        ),
    )
    parsed_field_names = (
        "row",
        "transaction_date",
        "description_detail",
        "billed_currency",
        "billed_amount",
        "original_currency",
        "original_amount",
        "section_category",
        "installment_number",
        "installment_amount",
        "header_profile",
    )
    records = (
        SourceRecord(
            outcome=RowOutcome.PARSED,
            reason_code="parsed",
            page_ordinal=1,
            section=SectionState.BILLED_INTERNATIONAL,
            row_group_ordinal=4,
            line_ordinals=(2, 3),
            token_ordinals=(10, 11),
            fields=fields(*parsed_field_names, multipage_name="row"),
            transaction_date=date(2026, 6, 15),
            description_detail="Synthetic international service",
            location=None,
            reference_authorization=None,
            billed_currency="CLP",
            billed_amount=Decimal("22303.00"),
            original_currency="USD",
            original_amount=Decimal("23.80"),
            section_category=FinancialCategory.PURCHASE_CHARGE,
            debt_effect=Decimal("22303.00"),
            installment_number=2,
            installment_amount=Decimal("11151.50"),
            header_profile="observed_v1_international",
        ),
        SourceRecord(
            outcome=RowOutcome.IGNORED,
            reason_code="card_identity_context",
            page_ordinal=2,
            section=SectionState.BILLED_INTERNATIONAL,
            row_group_ordinal=4,
            line_ordinals=(4,),
            token_ordinals=(21,),
            fields=fields("row"),
        ),
        SourceRecord(
            outcome=RowOutcome.REJECTED,
            reason_code="amount_ambiguous",
            page_ordinal=2,
            section=SectionState.BILLED_DOMESTIC,
            row_group_ordinal=4,
            line_ordinals=(5,),
            token_ordinals=(22,),
            fields=fields("row", "transaction_date"),
            transaction_date=date(2026, 6, 16),
        ),
    )
    reconciliation_fields = fields(
        "previous_balance",
        "current_billed_balance",
        "purchases_charges",
        "payments_credits",
        "financial_charges",
    )
    reconciliation = ReconciliationEvidence(
        status=ReconciliationStatus.RECONCILED,
        operands={
            "previous_balance": Decimal("100000.00"),
            "current_billed_balance": Decimal("112303.00"),
            "purchases_charges": Decimal("22303.00"),
            "payments_credits": Decimal("10000.00"),
            "financial_charges": Decimal("0.00"),
        },
        difference=Decimal("0.00"),
        fields=reconciliation_fields,
    )
    return TdcPdfParserResult(
        status=ParserStatus.RECOGNIZED,
        provider="Santander",
        product="credit_card",
        source_variant=SOURCE_VARIANT,
        parser_version=PARSER_VERSION,
        metadata=metadata,
        records=records,
        reconciliation=reconciliation,
        gir_version=GIR_VERSION,
        extraction_profile_version=PROFILE_VERSION,
    )


class SantanderTdcEvidenceProjectionTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        content = b"synthetic PDF identity only"
        self.artifact = SourceArtifact.objects.create(
            original_filename="synthetic-statement.pdf",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.batch = ImportBatch.objects.create(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            parser_version=PARSER_VERSION,
            status=ImportBatch.Status.PROCESSING,
        )

    def project(self, result: TdcPdfParserResult | None = None) -> ImportBatch:
        return _materialize_tdc_parser_evidence(
            import_batch=self.batch,
            parser_result=result or synthetic_result(),
        )

    def test_complete_parser_graph_projects_without_movements(self):
        batch = self.project()
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.PARTIAL)
        self.assertEqual((batch.parsed_count, batch.ignored_count, batch.rejected_count), (1, 1, 1))
        self.assertEqual((batch.opening_balance, batch.ending_balance), (Decimal("100000.00"), Decimal("112303.00")))
        self.assertEqual(batch.reconciliation_difference, Decimal("0.00"))
        self.assertEqual((batch.period_start, batch.period_end), (date(2026, 6, 1), date(2026, 6, 30)))

        raws = list(batch.raw_records.order_by("record_ordinal"))
        self.assertEqual([raw.record_ordinal for raw in raws], [1, 2, 3])
        self.assertEqual(
            [raw.parse_outcome for raw in raws],
            [RawRecord.ParseOutcome.PARSED, RawRecord.ParseOutcome.IGNORED, RawRecord.ParseOutcome.REJECTED],
        )
        self.assertTrue(all(raw.record_kind == RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD for raw in raws))
        self.assertTrue(all(raw.row_number is None and raw.raw_cells is None and raw.row_class is None for raw in raws))
        self.assertTrue(all(raw.xlsx_amount_source_column is None for raw in raws))
        self.assertTrue(all(hasattr(raw, "santander_tdc_pdf_evidence") for raw in raws))
        self.assertEqual(raws[2].santander_tdc_pdf_evidence.transaction_date, date(2026, 6, 16))
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=batch).exists())

        batch_evidence = batch.santander_tdc_pdf_evidence
        self.assertEqual(batch_evidence.card_last_four, "0079")
        self.assertEqual(batch_evidence.statement_currency, "CLP")
        self.assertEqual(batch_evidence.purchases_charges, Decimal("22303.00"))
        self.assertEqual(batch_evidence.payments_credits, Decimal("10000.00"))
        self.assertEqual(batch_evidence.financial_charges, Decimal("0.00"))
        self.assertEqual(batch_evidence.provenance_schema_version, PROVENANCE_SCHEMA_VERSION)
        self.assertEqual(
            batch_evidence.metadata_provenance["fields"]["card_last_four"]["role"],
            "card_last_four",
        )
        self.assertEqual(
            batch_evidence.reconciliation_provenance["fields"]["purchases_charges"]["role"],
            "purchases_charges",
        )
        self.assertEqual(batch_evidence.reconciliation_missing_operands, [])

        parsed = raws[0].santander_tdc_pdf_evidence
        self.assertEqual((parsed.billed_amount, parsed.billed_currency), (Decimal("22303.00"), "CLP"))
        self.assertEqual((parsed.original_amount, parsed.original_currency), (Decimal("23.80"), "USD"))
        self.assertEqual(parsed.debt_effect, Decimal("22303.00"))
        self.assertEqual((parsed.installment_number, parsed.installment_amount), (2, Decimal("11151.50")))
        self.assertNotIn("exchange_rate", {field.name for field in parsed._meta.fields})
        self.assertIsNone(parsed.location)
        self.assertIsNone(parsed.reference_authorization)
        spans = parsed.field_provenance["fields"]["row"]["additional_page_spans"]
        self.assertEqual([span["page_ordinal"] for span in spans], [2])
        self.assertEqual(parsed.field_provenance["fields"]["row"]["bbox"][0], "12.30")
        self.assertNotIsInstance(parsed.field_provenance["fields"]["row"]["bbox"][0], float)

    def test_repeated_row_groups_are_not_source_record_identity(self):
        batch = self.project()
        evidence = list(
            SantanderTdcPdfRecordEvidence.objects.filter(raw_record__import_batch=batch)
            .order_by("raw_record__record_ordinal")
        )
        self.assertEqual([item.row_group_ordinal for item in evidence], [4, 4, 4])
        self.assertEqual([item.raw_record.record_ordinal for item in evidence], [1, 2, 3])

    def test_payment_debt_reduction_remains_source_evidence_only(self):
        result = synthetic_result()
        payment = replace(
            result.records[0],
            section=SectionState.PAYMENTS_CREDITS,
            section_category=FinancialCategory.PAYMENT,
            original_amount=None,
            original_currency=None,
            debt_effect=Decimal("-22303.00"),
            fields={
                name: value
                for name, value in result.records[0].fields.items()
                if name not in {"original_amount", "original_currency"}
            },
        )
        batch = self.project(replace(result, records=(payment, *result.records[1:])))
        evidence = batch.raw_records.get(record_ordinal=1).santander_tdc_pdf_evidence
        self.assertEqual(evidence.debt_effect, Decimal("-22303.00"))
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=batch).exists())

    def test_projector_rejects_wrong_route_and_incomplete_provenance(self):
        self.batch.source_kind = ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX
        self.batch.save(update_fields=["source_kind"])
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_batch_source_kind_invalid"):
            self.project()

        self.batch.source_kind = ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF
        self.batch.save(update_fields=["source_kind"])
        result = synthetic_result()
        bad_record = replace(result.records[0], fields=fields("row"))
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_record_provenance_incomplete"):
            self.project(replace(result, records=(bad_record, *result.records[1:])))

    def test_projector_rejects_currency_and_debt_effect_mismatch(self):
        result = synthetic_result()
        currency_record = replace(result.records[0], billed_currency="USD")
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_parsed_record_invalid"):
            self.project(replace(result, records=(currency_record, *result.records[1:])))

        debt_record = replace(result.records[0], debt_effect=Decimal("-22303.00"))
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_debt_effect_invalid"):
            self.project(replace(result, records=(debt_record, *result.records[1:])))

    def test_projector_rejects_count_mismatch_atomically(self):
        manager_class = type(self.batch.raw_records)
        with patch.object(manager_class, "count", return_value=99):
            with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "projected_record_count_mismatch"):
                self.project()
        self.assertFalse(self.batch.raw_records.exists())
        self.assertFalse(SantanderTdcPdfBatchEvidence.objects.filter(import_batch=self.batch).exists())

    def test_projection_is_single_use_and_requires_exact_parser_version(self):
        self.project()
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_batch_already_projected"):
            self.project()

        second = ImportBatch.objects.create(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            parser_version="santander-tdc-pdf-v1",
            status=ImportBatch.Status.PROCESSING,
        )
        with self.assertRaisesRegex(SantanderTdcEvidenceProjectionError, "tdc_batch_parser_version_invalid"):
            _materialize_tdc_parser_evidence(import_batch=second, parser_result=synthetic_result())


class SantanderTdcEvidenceConstraintTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic current",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        content = b"structural synthetic"
        self.artifact = SourceArtifact.objects.create(
            original_filename="synthetic.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.xlsx_batch = ImportBatch.objects.create(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            status=ImportBatch.Status.PROCESSING,
        )

    def make_xlsx_raw(self, ordinal: int = 1) -> RawRecord:
        return RawRecord.objects.create(
            import_batch=self.xlsx_batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=ordinal,
            row_number=ordinal,
            raw_cells=[],
            row_class=RawRecord.RowClass.AUXILIARY,
            xlsx_amount_source_column=None,
            parse_outcome=RawRecord.ParseOutcome.IGNORED,
            parser_codes=["synthetic"],
        )

    def test_duplicate_record_ordinal_and_fake_pdf_spreadsheet_shape_fail(self):
        self.make_xlsx_raw()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_xlsx_raw()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RawRecord.objects.create(
                    import_batch=self.xlsx_batch,
                    record_kind=RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD,
                    record_ordinal=2,
                    row_number=2,
                    raw_cells=[],
                    row_class=RawRecord.RowClass.AUXILIARY,
                    parse_outcome=RawRecord.ParseOutcome.IGNORED,
                    parser_codes=["synthetic"],
                )

    def test_cross_source_evidence_ownership_fails_model_validation(self):
        raw = self.make_xlsx_raw()
        batch_evidence = SantanderTdcPdfBatchEvidence(
            import_batch=self.xlsx_batch,
            provenance_schema_version=PROVENANCE_SCHEMA_VERSION,
            gir_version=GIR_VERSION,
            extraction_profile_version=PROFILE_VERSION,
            billing_cutoff_date=date(2026, 6, 30),
            payment_due_date=date(2026, 7, 10),
            statement_currency="CLP",
            card_product_context="credit_card",
            card_last_four="0079",
            metadata_provenance=serialize_field_provenance_map({}),
            reconciliation_provenance=serialize_field_provenance_map({}),
        )
        with self.assertRaises(ValidationError):
            batch_evidence.full_clean()

        record_evidence = SantanderTdcPdfRecordEvidence(
            raw_record=raw,
            page_ordinal=1,
            section=SectionState.PREAMBLE.value,
            row_group_ordinal=0,
            line_ordinals=[1],
            token_ordinals=[1],
            field_provenance=serialize_field_provenance_map({"row": provenance("row")}),
        )
        with self.assertRaises(ValidationError):
            record_evidence.full_clean()

    def test_original_pair_card_shape_and_currency_constraints_fail_closed(self):
        card_account = Account.objects.create(
            display_name="Synthetic card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        batch = ImportBatch.objects.create(
            source_artifact=self.artifact,
            account=card_account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            parser_version=PARSER_VERSION,
            status=ImportBatch.Status.PROCESSING,
        )
        raw = RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD,
            record_ordinal=1,
            parse_outcome=RawRecord.ParseOutcome.REJECTED,
            parser_codes=["synthetic"],
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SantanderTdcPdfRecordEvidence.objects.create(
                    raw_record=raw,
                    page_ordinal=1,
                    section=SectionState.PREAMBLE.value,
                    row_group_ordinal=0,
                    line_ordinals=[1],
                    token_ordinals=[1],
                    field_provenance=serialize_field_provenance_map({"row": provenance("row")}),
                    original_amount=Decimal("23.80"),
                    original_currency=None,
                )

        invalid_batch_evidence = SantanderTdcPdfBatchEvidence(
            import_batch=batch,
            provenance_schema_version=PROVENANCE_SCHEMA_VERSION,
            gir_version=GIR_VERSION,
            extraction_profile_version=PROFILE_VERSION,
            billing_cutoff_date=date(2026, 6, 30),
            payment_due_date=date(2026, 7, 10),
            statement_currency="clp",
            card_product_context="credit_card",
            card_last_four="079",
            metadata_provenance=serialize_field_provenance_map({}),
            reconciliation_provenance=serialize_field_provenance_map({}),
        )
        with self.assertRaises(ValidationError):
            invalid_batch_evidence.full_clean()

    def test_provenance_rejects_floats_unknown_schema_and_invalid_ordinals(self):
        payload = serialize_field_provenance_map({"row": provenance("row")})
        float_payload = {
            **payload,
            "fields": {
                "row": {
                    **payload["fields"]["row"],
                    "bbox": [1.0, "24.50", "120.75", "36.90"],
                }
            },
        }
        with self.assertRaises(SantanderTdcProvenanceError):
            validate_field_provenance_payload(float_payload)
        with self.assertRaises(SantanderTdcProvenanceError):
            validate_field_provenance_payload({**payload, "schema": "future-schema"})
        invalid_ordinal = {
            **payload,
            "fields": {
                "row": {
                    **payload["fields"]["row"],
                    "line_ordinals": [0],
                }
            },
        }
        with self.assertRaises(SantanderTdcProvenanceError):
            validate_field_provenance_payload(invalid_ordinal)
