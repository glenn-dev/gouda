from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import logging
from unittest.mock import patch

from django.db import DatabaseError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from gouda.ledger.models import (
    Account,
    ImportBatch,
    Movement,
    SantanderTdcAccountBinding,
    SantanderTdcPdfBatchEvidence,
    SantanderTdcPdfRecordEvidence,
    SourceArtifact,
)
from gouda.ledger.services import santander_tdc_import as service
from gouda.santander_tdc_pdf.extraction import ConformanceCode, ExtractionError
from gouda.santander_tdc_pdf.parser import (
    PARSER_VERSION,
    ContradictoryTdcPdfError,
    UnsupportedTdcPdfError,
)
from gouda.santander_tdc_pdf.types import (
    FinancialCategory,
    ParserStatus,
    ReconciliationEvidence,
    ReconciliationStatus,
    RowOutcome,
    SectionState,
)
from tests.ledger.test_santander_tdc_evidence import provenance, synthetic_result


_MISSING_OPERANDS = (
    "previous_balance",
    "current_billed_balance",
    "purchases_charges",
    "payments_credits",
    "financial_charges",
)


def recognized_result(*, records=None, reconciliation=None):
    result = synthetic_result()
    return replace(
        result,
        records=result.records if records is None else tuple(records),
        reconciliation=(
            result.reconciliation if reconciliation is None else reconciliation
        ),
    )


def insufficient_reconciliation():
    return ReconciliationEvidence(
        status=ReconciliationStatus.INSUFFICIENT_DATA,
        operands={},
        missing_operands=_MISSING_OPERANDS,
        fields={},
    )


class SantanderTdcImportServiceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic TDC account",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        self.binding = service.configure_santander_tdc_account_binding(
            account=self.account,
            card_last_four="0079",
        )
        self.content = b"synthetic TDC service bytes"

    def import_content(self, *, content=None, account=None, result=None, filename="synthetic.pdf"):
        with patch.object(
            service,
            "parse_tdc_pdf",
            return_value=result or synthetic_result(),
        ):
            return service.import_santander_credit_card_pdf(
                content=self.content if content is None else content,
                original_filename=filename,
                account=account or self.account,
            )

    def assert_fatal(self, batch, *, stage, code, variant=None):
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.FATAL)
        self.assertEqual(batch.failure_stage, stage)
        self.assertEqual(batch.failure_code, code)
        self.assertEqual(batch.source_variant, variant)
        self.assertEqual(
            (batch.parsed_count, batch.ignored_count, batch.rejected_count),
            (0, 0, 0),
        )
        self.assertIsNone(batch.duplicate_of_id)
        self.assertIsNone(batch.reconciliation_status)
        self.assertFalse(batch.raw_records.exists())
        self.assertFalse(
            SantanderTdcPdfBatchEvidence.objects.filter(import_batch=batch).exists()
        )
        self.assertFalse(
            Movement.objects.filter(raw_record__import_batch=batch).exists()
        )

    def test_binding_configuration_is_idempotent_and_never_overwrites(self):
        same = service.configure_santander_tdc_account_binding(
            account=self.account,
            card_last_four="0079",
        )
        self.assertEqual(same.pk, self.binding.pk)
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.configure_santander_tdc_account_binding(
                account=self.account,
                card_last_four="0080",
            )
        self.assertEqual(context.exception.code, "account_binding_conflict")
        self.binding.refresh_from_db()
        self.assertEqual(self.binding.card_last_four, "0079")
        self.assertNotIn("0080", str(context.exception))

    def test_binding_configuration_validates_account_suffix_and_transaction_context(self):
        current = Account.objects.create(
            display_name="Synthetic current",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.configure_santander_tdc_account_binding(
                account=current,
                card_last_four="1234",
            )
        self.assertEqual(context.exception.code, "account_kind_unsupported")

        invalid_orientation = Account(
            pk=self.account.pk,
            display_name="Synthetic invalid orientation",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        invalid_orientation._state.adding = False
        with patch.object(service, "_lock_account", return_value=invalid_orientation):
            with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                service.configure_santander_tdc_account_binding(
                    account=self.account,
                    card_last_four="0079",
                )
        self.assertEqual(context.exception.code, "account_orientation_unsupported")

        for suffix in ("123", "12345", "12A4", "１２３４"):
            with self.subTest(suffix_length=len(suffix)):
                with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                    service.configure_santander_tdc_account_binding(
                        account=self.account,
                        card_last_four=suffix,
                    )
                self.assertEqual(context.exception.code, "card_last_four_invalid")

        with transaction.atomic(), self.assertRaises(
            service.SantanderTdcImportServiceError
        ) as context:
            service.configure_santander_tdc_account_binding(
                account=self.account,
                card_last_four="0079",
            )
        self.assertEqual(context.exception.code, "transaction_context_unsupported")

    def test_partial_import_persists_complete_evidence_and_canonical_movement(self):
        batch = self.import_content()
        self.assertEqual(batch.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(
            (batch.parsed_count, batch.ignored_count, batch.rejected_count),
            (1, 1, 1),
        )
        self.assertEqual(batch.source_kind, ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF)
        self.assertEqual(batch.parser_version, PARSER_VERSION)
        self.assertEqual(batch.source_variant, "santander_credit_card_pdf")
        self.assertEqual(batch.raw_records.count(), 3)
        self.assertEqual(
            SantanderTdcPdfRecordEvidence.objects.filter(
                raw_record__import_batch=batch
            ).count(),
            3,
        )
        movement = Movement.objects.get(raw_record__import_batch=batch)
        evidence = movement.raw_record.santander_tdc_pdf_evidence
        self.assertEqual(movement.account_id, self.account.pk)
        self.assertEqual(movement.occurrence_date, evidence.transaction_date)
        self.assertEqual(movement.signed_amount, Decimal("-22303.00"))
        self.assertEqual(movement.currency, "CLP")
        self.assertEqual(movement.description, evidence.description_detail)
        self.assertIsNone(movement.source_reference)
        self.assertIsNone(movement.running_balance)
        self.assertEqual((evidence.original_amount, evidence.original_currency), (Decimal("23.80"), "USD"))
        self.assertEqual((evidence.billed_amount, evidence.billed_currency), (Decimal("22303.00"), "CLP"))
        self.assertEqual(batch.santander_tdc_pdf_evidence.card_last_four, "0079")
        self.assertFalse(hasattr(movement, "original_amount"))
        self.assertFalse(hasattr(movement, "exchange_rate"))

    def test_every_supported_category_maps_signed_amount_from_debt_effect(self):
        base = synthetic_result().records[0]
        categories = tuple(FinancialCategory)
        records = []
        expected = []
        for index, category in enumerate(categories, 1):
            is_reduction = category in {
                FinancialCategory.PAYMENT,
                FinancialCategory.CREDIT_REFUND,
            }
            debt_effect = Decimal("-10.00") if is_reduction else Decimal("10.00")
            records.append(
                replace(
                    base,
                    page_ordinal=index,
                    row_group_ordinal=index,
                    section=(
                        SectionState.PAYMENTS_CREDITS
                        if is_reduction
                        else SectionState.BILLED_OTHER
                    ),
                    section_category=category,
                    billed_amount=Decimal("10.00"),
                    debt_effect=debt_effect,
                    original_amount=None,
                    original_currency=None,
                    installment_number=None,
                    installment_amount=None,
                    fields={
                        name: value
                        for name, value in base.fields.items()
                        if name
                        not in {
                            "original_amount",
                            "original_currency",
                            "installment_number",
                            "installment_amount",
                        }
                    },
                )
            )
            expected.append(-debt_effect)
        result = recognized_result(
            records=records,
            reconciliation=insufficient_reconciliation(),
        )
        batch = self.import_content(result=result)
        movements = list(
            Movement.objects.filter(raw_record__import_batch=batch).order_by(
                "raw_record__record_ordinal"
            )
        )
        self.assertEqual(batch.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual([movement.signed_amount for movement in movements], expected)
        self.assertEqual(
            [
                movement.raw_record.santander_tdc_pdf_evidence.section_category
                for movement in movements
            ],
            [category.value for category in categories],
        )

    def test_optional_reference_is_preserved_without_fabricating_running_balance(self):
        source = synthetic_result()
        record = replace(
            source.records[0],
            reference_authorization="SYNTHETIC-REFERENCE",
            fields={
                **source.records[0].fields,
                "reference_authorization": provenance("reference_authorization"),
            },
        )
        batch = self.import_content(
            content=b"synthetic optional reference",
            result=recognized_result(
                records=(record,),
                reconciliation=insufficient_reconciliation(),
            ),
        )
        movement = Movement.objects.get(raw_record__import_batch=batch)
        self.assertEqual(movement.source_reference, "SYNTHETIC-REFERENCE")
        self.assertIsNone(movement.running_balance)

    def test_row_status_mapping_including_all_ignored_zero_movement(self):
        source = synthetic_result()
        cases = (
            ((source.records[0],), ImportBatch.Status.ACCEPTED, 1),
            (source.records, ImportBatch.Status.PARTIAL, 1),
            ((source.records[2],), ImportBatch.Status.REJECTED, 0),
            ((source.records[1],), ImportBatch.Status.ACCEPTED, 0),
        )
        for index, (records, expected_status, movement_count) in enumerate(cases):
            with self.subTest(status=expected_status):
                result = recognized_result(
                    records=records,
                    reconciliation=insufficient_reconciliation(),
                )
                batch = self.import_content(
                    content=f"synthetic-status-{index}".encode(),
                    result=result,
                )
                self.assertEqual(batch.status, expected_status)
                self.assertEqual(
                    Movement.objects.filter(raw_record__import_batch=batch).count(),
                    movement_count,
                )

    def test_all_reconciliation_states_persist_and_not_reconciled_keeps_movement(self):
        source = synthetic_result()
        parsed = (source.records[0],)
        operands = dict(source.reconciliation.operands)
        reconciled = replace(
            source.reconciliation,
            status=ReconciliationStatus.RECONCILED,
            difference=Decimal("0.00"),
        )
        not_reconciled_operands = {
            **operands,
            "current_billed_balance": Decimal("112302.00"),
        }
        cases = (
            reconciled,
            replace(
                reconciled,
                status=ReconciliationStatus.NOT_RECONCILED,
                operands=not_reconciled_operands,
                difference=Decimal("1.00"),
            ),
            insufficient_reconciliation(),
            ReconciliationEvidence(
                status=ReconciliationStatus.NOT_APPLICABLE,
                operands={},
                fields={},
            ),
        )
        for index, reconciliation in enumerate(cases):
            with self.subTest(status=reconciliation.status):
                batch = self.import_content(
                    content=f"synthetic-reconciliation-{index}".encode(),
                    result=recognized_result(
                        records=parsed,
                        reconciliation=reconciliation,
                    ),
                )
                self.assertEqual(batch.reconciliation_status, reconciliation.status.value)
                self.assertEqual(
                    Movement.objects.filter(raw_record__import_batch=batch).count(),
                    1,
                )

    def test_malformed_reconciliation_unbilled_and_zero_debt_are_boundary_fatal(self):
        source = synthetic_result()
        malformed_reconciliation = replace(
            source.reconciliation,
            difference=Decimal("1.00"),
        )
        cases = (
            (
                recognized_result(reconciliation=malformed_reconciliation),
                "tdc_reconciliation_invalid",
            ),
            (
                recognized_result(
                    reconciliation=replace(
                        source.reconciliation,
                        status=ReconciliationStatus.RECONCILED,
                        difference=Decimal("0.00"),
                    )
                ),
                "tdc_reconciliation_invalid",
            ),
            (
                recognized_result(
                    records=(replace(source.records[0], section=SectionState.UNBILLED),),
                    reconciliation=insufficient_reconciliation(),
                ),
                "tdc_unbilled_parsed",
            ),
            (
                recognized_result(
                    records=(
                        replace(
                            source.records[0],
                            billed_amount=Decimal("0.00"),
                            debt_effect=Decimal("0.00"),
                        ),
                    ),
                    reconciliation=insufficient_reconciliation(),
                ),
                "tdc_parsed_record_invalid",
            ),
            (
                recognized_result(
                    records=(
                        replace(
                            source.records[1],
                            reason_code="PRIVATE_UNTRUSTED_REASON",
                        ),
                    ),
                    reconciliation=insufficient_reconciliation(),
                ),
                "tdc_record_reason_invalid",
            ),
        )
        for index, (result, code) in enumerate(cases):
            with self.subTest(code=code):
                batch = self.import_content(
                    content=f"synthetic-invalid-graph-{index}".encode(),
                    result=result,
                )
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.BOUNDARY,
                    code=code,
                    variant="santander_credit_card_pdf",
                )

    def test_binding_mismatch_is_sanitized_boundary_fatal(self):
        result = synthetic_result()
        metadata = replace(result.metadata, card_last_four="0080")
        batch = self.import_content(result=replace(result, metadata=metadata))
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.CARD_BINDING_MISMATCH,
            variant="santander_credit_card_pdf",
        )
        self.assertNotIn("0079", str(batch.failure_code))
        self.assertNotIn("0080", str(batch.failure_code))

    def test_statement_currency_must_match_trusted_account_currency(self):
        usd_account = Account.objects.create(
            display_name="Synthetic USD card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="USD",
        )
        service.configure_santander_tdc_account_binding(
            account=usd_account,
            card_last_four="0079",
        )
        batch = self.import_content(
            account=usd_account,
            content=b"synthetic CLP statement for USD account",
        )
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code="tdc_statement_currency_mismatch",
            variant="santander_credit_card_pdf",
        )

    def test_service_preconditions_fail_before_registration(self):
        invalid_content = (b"", bytearray(b"x"), memoryview(b"x"), "path.pdf")
        for value in invalid_content:
            with self.subTest(content_type=type(value).__name__):
                with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                    service.import_santander_credit_card_pdf(
                        content=value,
                        original_filename="synthetic.pdf",
                        account=self.account,
                    )
                expected = "content_empty" if value == b"" else "content_type_invalid"
                self.assertEqual(context.exception.code, expected)

        for filename in (None, "", "   ", "/path/", ".", "..", "bad\x00.pdf", "x" * 256):
            with self.subTest(filename_type=type(filename).__name__):
                with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                    service.import_santander_credit_card_pdf(
                        content=b"different",
                        original_filename=filename,
                        account=self.account,
                    )
                self.assertEqual(context.exception.code, "filename_invalid")

        unsaved = Account(
            display_name="Unsaved",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.import_santander_credit_card_pdf(
                content=b"different",
                original_filename="synthetic.pdf",
                account=unsaved,
            )
        self.assertEqual(context.exception.code, "account_not_persisted")

        missing_binding = Account.objects.create(
            display_name="Unbound card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.import_santander_credit_card_pdf(
                content=b"different",
                original_filename="synthetic.pdf",
                account=missing_binding,
            )
        self.assertEqual(context.exception.code, "account_binding_missing")
        self.assertFalse(SourceArtifact.objects.exists())

    def test_account_context_preconditions_are_stable(self):
        current = Account.objects.create(
            display_name="Current",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.import_santander_credit_card_pdf(
                content=b"different",
                original_filename="synthetic.pdf",
                account=current,
            )
        self.assertEqual(context.exception.code, "account_kind_unsupported")

        fake = Account(
            pk=self.account.pk,
            display_name="Fake",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        fake._state.adding = False
        with patch.object(service, "_load_account", return_value=fake):
            with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                service.import_santander_credit_card_pdf(
                    content=b"different-orientation",
                    original_filename="synthetic.pdf",
                    account=self.account,
                )
        self.assertEqual(context.exception.code, "account_orientation_unsupported")

        fake.economic_orientation = Account.EconomicOrientation.LIABILITY
        fake.currency = "clp"
        with patch.object(service, "_load_account", return_value=fake):
            with self.assertRaises(service.SantanderTdcImportServiceError) as context:
                service.import_santander_credit_card_pdf(
                    content=b"different-currency",
                    original_filename="synthetic.pdf",
                    account=self.account,
                )
        self.assertEqual(context.exception.code, "account_currency_invalid")

        deleted = Account.objects.create(
            display_name="Deleted card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        deleted_id = deleted.pk
        deleted.delete()
        deleted = Account(
            pk=deleted_id,
            display_name="Deleted card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        deleted._state.adding = False
        with self.assertRaises(service.SantanderTdcImportServiceError) as context:
            service.import_santander_credit_card_pdf(
                content=b"different-deleted",
                original_filename="synthetic.pdf",
                account=deleted,
            )
        self.assertEqual(context.exception.code, "account_not_found")

    def test_parser_and_extraction_failures_are_whitelisted_and_durable(self):
        failures = (
            (ExtractionError(ConformanceCode.INVALID_PDF), "invalid_pdf"),
            (
                UnsupportedTdcPdfError("provider_product_context_missing"),
                "provider_product_context_missing",
            ),
            (
                ContradictoryTdcPdfError("card_identity_conflict"),
                "card_identity_conflict",
            ),
            (UnsupportedTdcPdfError("PRIVATE_UNKNOWN_CODE"), service.TDC_PARSER_ERROR_UNRECOGNIZED),
            (RuntimeError("PRIVATE_EXCEPTION_TEXT"), service.TDC_PARSER_UNEXPECTED),
        )
        for index, (error, code) in enumerate(failures):
            with self.subTest(code=code), patch.object(
                service,
                "parse_tdc_pdf",
                side_effect=error,
            ):
                batch = service.import_santander_credit_card_pdf(
                    content=f"synthetic-parser-failure-{index}".encode(),
                    original_filename="private-name.pdf",
                    account=self.account,
                )
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.PARSER,
                    code=code,
                )

        fatal_result = replace(
            synthetic_result(),
            status=ParserStatus.FATAL,
            errors=("card_identity_conflict",),
        )
        batch = self.import_content(
            content=b"synthetic-fatal-result",
            result=fatal_result,
        )
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.PARSER,
            code="card_identity_conflict",
            variant="santander_credit_card_pdf",
        )

    def test_non_pdf_bytes_use_existing_extraction_boundary(self):
        batch = service.import_santander_credit_card_pdf(
            content=b"not a PDF",
            original_filename="not-required.pdf",
            account=self.account,
        )
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.PARSER,
            code="invalid_pdf",
        )

    def test_sequential_duplicate_and_fatal_retry_lifecycle(self):
        first = self.import_content()
        duplicate = self.import_content()
        self.assertEqual(first.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(duplicate.status, ImportBatch.Status.DUPLICATE)
        self.assertEqual(duplicate.duplicate_of_id, first.pk)
        self.assertEqual(duplicate.source_variant, first.source_variant)
        self.assertFalse(duplicate.raw_records.exists())
        self.assertFalse(
            SantanderTdcPdfBatchEvidence.objects.filter(import_batch=duplicate).exists()
        )

        retry_content = b"synthetic retry bytes"
        with patch.object(
            service,
            "parse_tdc_pdf",
            side_effect=UnsupportedTdcPdfError("statement_context_missing"),
        ):
            fatal = service.import_santander_credit_card_pdf(
                content=retry_content,
                original_filename="synthetic.pdf",
                account=self.account,
            )
        successful = self.import_content(content=retry_content)
        self.assertEqual(fatal.status, ImportBatch.Status.FATAL)
        self.assertEqual(successful.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(fatal.source_artifact_id, successful.source_artifact_id)

    def test_existing_other_route_materialization_is_source_kind_conflict(self):
        content = b"synthetic cross-route artifact"
        artifact = SourceArtifact.objects.create(
            original_filename="synthetic.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        ImportBatch.objects.create(
            source_artifact=artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=timezone.now(),
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        conflict = self.import_content(content=content)
        self.assert_fatal(
            conflict,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.SOURCE_KIND_CONFLICT,
        )

    def test_other_route_fatal_history_does_not_block_correct_tdc_import(self):
        content = b"synthetic wrong-route fatal history"
        artifact = SourceArtifact.objects.create(
            original_filename="synthetic.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        wrong_route = ImportBatch.objects.create(
            source_artifact=artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            status=ImportBatch.Status.FATAL,
            completed_at=timezone.now(),
            failure_stage=ImportBatch.FailureStage.PARSER,
            failure_code="xlsx_invalid",
        )
        successful = self.import_content(content=content)
        self.assertEqual(wrong_route.status, ImportBatch.Status.FATAL)
        self.assertEqual(successful.status, ImportBatch.Status.PARTIAL)
        self.assertEqual(wrong_route.source_artifact_id, successful.source_artifact_id)

    def test_other_route_winner_created_after_parse_becomes_source_kind_conflict(self):
        result = synthetic_result()

        def create_other_route_winner(_content):
            artifact = SourceArtifact.objects.get()
            ImportBatch.objects.create(
                source_artifact=artifact,
                account=self.account,
                source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                parser_version="santander-v0.2",
                source_variant="v1",
                status=ImportBatch.Status.ACCEPTED,
                completed_at=timezone.now(),
                reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
            )
            return result

        with patch.object(service, "parse_tdc_pdf", side_effect=create_other_route_winner):
            conflict = service.import_santander_credit_card_pdf(
                content=b"synthetic post-parse route race",
                original_filename="synthetic.pdf",
                account=self.account,
            )
        self.assert_fatal(
            conflict,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.SOURCE_KIND_CONFLICT,
            variant="santander_credit_card_pdf",
        )

    def test_parser_version_and_source_variant_are_not_accepted_by_best_effort(self):
        source = synthetic_result()
        for index, (result, expected_variant) in enumerate(
            (
                (replace(source, parser_version="santander-tdc-pdf-v2"), "santander_credit_card_pdf"),
                (replace(source, source_variant="future_variant"), None),
            )
        ):
            batch = self.import_content(
                content=f"synthetic-version-{index}".encode(),
                result=result,
            )
            self.assert_fatal(
                batch,
                stage=ImportBatch.FailureStage.BOUNDARY,
                code="tdc_parser_result_invalid",
                variant=expected_variant,
            )

    def test_account_and_binding_changes_after_parse_are_boundary_fatal(self):
        real_result = synthetic_result()

        def change_account(_content):
            Account.objects.filter(pk=self.account.pk).update(currency="USD")
            return real_result

        with patch.object(service, "parse_tdc_pdf", side_effect=change_account):
            batch = service.import_santander_credit_card_pdf(
                content=b"synthetic-account-change",
                original_filename="synthetic.pdf",
                account=self.account,
            )
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.ACCOUNT_CONTEXT_CHANGED,
            variant="santander_credit_card_pdf",
        )
        Account.objects.filter(pk=self.account.pk).update(currency="CLP")

        def change_binding(_content):
            SantanderTdcAccountBinding.objects.filter(pk=self.binding.pk).update(
                card_last_four="0080"
            )
            return real_result

        with patch.object(service, "parse_tdc_pdf", side_effect=change_binding):
            batch = service.import_santander_credit_card_pdf(
                content=b"synthetic-binding-change",
                original_filename="synthetic.pdf",
                account=self.account,
            )
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.CARD_BINDING_MISMATCH,
            variant="santander_credit_card_pdf",
        )

    def test_materialization_failures_roll_back_graph_and_compensate(self):
        seams = (
            "_persist_prepared_tdc_evidence",
            "_create_movements",
            "_finalize_prepared_tdc_batch",
        )
        for index, seam in enumerate(seams):
            original = getattr(service, seam)

            def fail_after(*args, __original=original, **kwargs):
                __original(*args, **kwargs)
                raise RuntimeError("PRIVATE_MATERIALIZATION_FAILURE")

            with self.subTest(seam=seam), patch.object(
                service,
                seam,
                side_effect=fail_after,
            ):
                batch = self.import_content(
                    content=f"synthetic-materialization-{index}".encode()
                )
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.PERSISTENCE,
                    code=service.MATERIALIZATION_FAILED,
                    variant="santander_credit_card_pdf",
                )

    def test_database_and_compensation_failures_use_only_safe_codes(self):
        with patch.object(
            service,
            "_persist_prepared_tdc_evidence",
            side_effect=DatabaseError("PRIVATE_DATABASE_TEXT"),
        ):
            batch = self.import_content(content=b"synthetic-db-failure")
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.PERSISTENCE,
            code=service.MATERIALIZATION_DATABASE_ERROR,
            variant="santander_credit_card_pdf",
        )

        original_save = ImportBatch.save

        def reject_fatal(instance, *args, **kwargs):
            if instance.status == ImportBatch.Status.FATAL:
                raise DatabaseError("PRIVATE_COMPENSATION_TEXT")
            return original_save(instance, *args, **kwargs)

        with patch.object(
            service,
            "parse_tdc_pdf",
            side_effect=RuntimeError("PRIVATE_PARSER_TEXT"),
        ), patch.object(ImportBatch, "save", new=reject_fatal):
            with self.assertRaises(service.SantanderTdcImportOperationalError) as context:
                service.import_santander_credit_card_pdf(
                    content=b"synthetic-compensation-failure",
                    original_filename="private.pdf",
                    account=self.account,
                )
        self.assertEqual(context.exception.code, "fatal_compensation_failed")
        self.assertEqual(str(context.exception), "fatal_compensation_failed")

    def test_private_source_values_never_reach_failure_surfaces_or_logs(self):
        sentinels = (
            "PRIVATE_FILENAME",
            "PRIVATE_CARD_SUFFIX",
            "PRIVATE_DESCRIPTION",
            "PRIVATE_REFERENCE",
            "PRIVATE_AMOUNT",
            "PRIVATE_EXCEPTION_TEXT",
        )
        with patch.object(logging.Logger, "_log") as log_call, patch.object(
            service,
            "parse_tdc_pdf",
            side_effect=RuntimeError(sentinels[-1]),
        ):
            batch = service.import_santander_credit_card_pdf(
                content=b"private synthetic source content",
                original_filename=f"/private/{sentinels[0]}.pdf",
                account=self.account,
            )
        rendered = " ".join(
            (
                batch.failure_stage or "",
                batch.failure_code or "",
                str(batch),
                repr(batch),
            )
        )
        log_call.assert_not_called()
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)

    def test_call_inside_existing_transaction_fails_before_registration(self):
        with transaction.atomic(), self.assertRaises(
            service.SantanderTdcImportServiceError
        ) as context:
            service.import_santander_credit_card_pdf(
                content=b"different",
                original_filename="synthetic.pdf",
                account=self.account,
            )
        self.assertEqual(context.exception.code, "transaction_context_unsupported")
