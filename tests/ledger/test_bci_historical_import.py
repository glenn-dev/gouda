from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase

from gouda.bci_historical_pdf import parse_bci_historical_pdf
from gouda.ledger.models import (
    Account,
    BciHistoricalPdfBatchEvidence,
    FinancialObservation,
    ImportBatch,
    Movement,
    RawRecord,
)
from gouda.ledger.services.bci_historical_import import (
    import_bci_historical_current_account_pdf,
)
from gouda.ledger.services.bci_historical_policy import (
    resolve_bci_historical_batch,
    resolve_bci_historical_observation,
)
from gouda.ledger.services.observation_resolution import create_financial_observation
from tests.fixtures.bci_historical import synthetic_bci_historical_pdf


class BciHistoricalImportTests(TransactionTestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic BCI",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )

    def import_rows(self, rows, **kwargs):
        content = synthetic_bci_historical_pdf(rows=tuple(rows), **kwargs)
        parsed = parse_bci_historical_pdf(content)
        return import_bci_historical_current_account_pdf(
            content=content,
            original_filename="synthetic.pdf",
            account=self.account,
            expected_source_account_id=parsed.metadata.source_account_id,
        )

    def test_parsed_is_unresolved_and_does_not_create_canonical_movement(self):
        batch = self.import_rows((
            {"date": date(2026, 1, 2), "debit": 1000},
            {"date": date(2026, 1, 3), "credit": 2000},
        ))
        self.assertEqual(batch.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(batch.reconciliation_status, ImportBatch.ReconciliationStatus.RECONCILED)
        self.assertEqual(batch.parsed_count, 2)
        self.assertEqual(FinancialObservation.objects.filter(raw_record__import_batch=batch).count(), 2)
        self.assertEqual(Movement.objects.filter(account=self.account).count(), 0)
        self.assertEqual(resolve_bci_historical_batch(import_batch_id=batch.pk).__len__(), 2)
        self.assertEqual(Movement.objects.filter(account=self.account).count(), 2)

    def test_reconciliation_failure_preserves_observations_but_policy_abstains(self):
        batch = self.import_rows(({"date": date(2026, 1, 2), "debit": 1000},), closing_override=99999)
        self.assertEqual(batch.reconciliation_status, ImportBatch.ReconciliationStatus.NOT_RECONCILED)
        self.assertEqual(FinancialObservation.objects.filter(raw_record__import_batch=batch).count(), 1)
        self.assertEqual(resolve_bci_historical_batch(import_batch_id=batch.pk), ())
        self.assertEqual(Movement.objects.filter(account=self.account).count(), 0)

    def test_account_mismatch_stops_before_observations(self):
        content = synthetic_bci_historical_pdf(rows=({"debit": 1000},))
        batch = import_bci_historical_current_account_pdf(
            content=content,
            original_filename="synthetic.pdf",
            account=self.account,
            expected_source_account_id="900000000999",
        )
        self.assertEqual(batch.status, ImportBatch.Status.FATAL)
        self.assertEqual(batch.failure_code, "source_account_mismatch")
        self.assertEqual(FinancialObservation.objects.count(), 0)

    def test_exact_retry_is_duplicate_without_new_observations(self):
        content = synthetic_bci_historical_pdf(rows=({"debit": 1000},))
        expected = parse_bci_historical_pdf(content).metadata.source_account_id
        first = import_bci_historical_current_account_pdf(content=content, original_filename="one.pdf", account=self.account, expected_source_account_id=expected)
        second = import_bci_historical_current_account_pdf(content=content, original_filename="two.pdf", account=self.account, expected_source_account_id=expected)
        self.assertEqual(second.status, ImportBatch.Status.DUPLICATE)
        self.assertEqual(second.duplicate_of_id, first.pk)
        self.assertEqual(FinancialObservation.objects.count(), 1)
        self.assertEqual(Movement.objects.count(), 0)

    def test_parser_failure_can_be_followed_by_valid_artifact(self):
        failed = import_bci_historical_current_account_pdf(
            content=b"%PDF-1.4\ncorrupt",
            original_filename="synthetic-corrupt.pdf",
            account=self.account,
            expected_source_account_id="900000000001",
        )
        self.assertEqual(failed.status, ImportBatch.Status.FATAL)
        valid_content = synthetic_bci_historical_pdf(rows=({"debit": 1000},))
        valid = import_bci_historical_current_account_pdf(
            content=valid_content,
            original_filename="synthetic-valid.pdf",
            account=self.account,
            expected_source_account_id="900000000001",
        )
        self.assertEqual(valid.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(FinancialObservation.objects.count(), 1)

    def test_missing_reconciliation_operand_is_durable_evidence(self):
        batch = self.import_rows(({"debit": 1000},), omit_summary_operand="credits")
        evidence = BciHistoricalPdfBatchEvidence.objects.get(import_batch=batch)
        self.assertEqual(evidence.reconciliation_missing_operands, ["printed_total_credits"])
        self.assertEqual(batch.reconciliation_status, ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA)
        self.assertEqual(FinancialObservation.objects.count(), 1)

    def test_materialization_failure_rolls_back_raw_evidence_and_observation(self):
        content = synthetic_bci_historical_pdf(rows=({"debit": 1000},))
        with patch(
            "gouda.ledger.services.bci_historical_import.BciHistoricalPdfRecordEvidence.full_clean",
            side_effect=RuntimeError("synthetic materialization failure"),
        ):
            batch = import_bci_historical_current_account_pdf(
                content=content,
                original_filename="synthetic-rollback.pdf",
                account=self.account,
                expected_source_account_id="900000000001",
            )
        self.assertEqual(batch.status, ImportBatch.Status.FATAL)
        self.assertEqual(batch.failure_code, "bci_materialization_failed")
        self.assertEqual(batch.raw_records.count(), 0)
        self.assertFalse(BciHistoricalPdfBatchEvidence.objects.filter(import_batch=batch).exists())
        self.assertEqual(FinancialObservation.objects.count(), 0)

    def test_two_same_statement_identical_tuples_are_distinct(self):
        batch = self.import_rows((
            {"date": date(2026, 1, 2), "debit": 1000, "reference": "same"},
            {"date": date(2026, 1, 2), "debit": 1000, "reference": "same"},
        ))
        self.assertEqual(len(resolve_bci_historical_batch(import_batch_id=batch.pk)), 2)
        self.assertEqual(Movement.objects.filter(account=self.account).count(), 2)

    def test_cross_batch_collision_abstains(self):
        first = self.import_rows(({"date": date(2026, 1, 2), "debit": 1000},))
        resolve_bci_historical_batch(import_batch_id=first.pk)
        second = self.import_rows(({"date": date(2026, 1, 2), "debit": 1000},), source_account_id="900000000002")
        self.assertEqual(resolve_bci_historical_batch(import_batch_id=second.pk), ())
        self.assertEqual(Movement.objects.filter(account=self.account).count(), 1)

    def test_bci_batch_evidence_protects_import_batch_deletion(self):
        batch = self.import_rows(({"date": date(2026, 1, 2), "debit": 1000},))
        self.assertTrue(BciHistoricalPdfBatchEvidence.objects.filter(import_batch=batch).exists())
        with self.assertRaises(ProtectedError):
            batch.delete()

    def test_historical_policy_rejects_forged_observation_claim(self):
        batch = self.import_rows(({"date": date(2026, 1, 2), "debit": 1000},))
        raw = RawRecord.objects.get(import_batch=batch, parse_outcome=RawRecord.ParseOutcome.PARSED)
        forged = create_financial_observation(
            raw_record_id=raw.pk,
            account_id=self.account.pk,
            transaction_date=None,
            accounting_date=date(2026, 1, 3),
            signed_amount=Decimal("-1000.00"),
            currency="CLP",
            description="synthetic forged claim",
            source_reference=None,
            interpretation_method="bci_historical_current_account_pdf",
            interpretation_version="bci-historical-current-account-pdf-v1",
            idempotency_key=uuid4(),
        )
        self.assertIsNone(resolve_bci_historical_observation(observation_id=forged.pk))
        self.assertEqual(FinancialObservation.objects.get(pk=forged.pk).state, FinancialObservation.State.UNRESOLVED)
        self.assertEqual(Movement.objects.count(), 0)
