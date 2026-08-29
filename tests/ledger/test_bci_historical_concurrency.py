from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from gouda.bci_historical_pdf import parse_bci_historical_pdf
from gouda.ledger.models import FinancialObservation, ImportBatch, Movement, ObservationResolution
from gouda.ledger.services.bci_historical_import import import_bci_historical_current_account_pdf
from gouda.ledger.services.bci_historical_policy import resolve_bci_historical_batch, resolve_bci_historical_observation
from tests.fixtures.bci_historical import synthetic_bci_historical_pdf


class BciHistoricalConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        from gouda.ledger.models import Account

        self.account = Account.objects.create(
            display_name="Synthetic concurrent BCI account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        self.content = synthetic_bci_historical_pdf(rows=({"date": date(2026, 1, 2), "debit": 1000},))
        self.expected = parse_bci_historical_pdf(self.content).metadata.source_account_id

    def _import_worker(self, name):
        close_old_connections()
        try:
            account = type(self.account).objects.get(pk=self.account.pk)
            return import_bci_historical_current_account_pdf(
                content=self.content,
                original_filename=name,
                account=account,
                expected_source_account_id=self.expected,
            ).status
        finally:
            close_old_connections()

    def test_concurrent_exact_artifact_import_has_one_materialized_batch(self):
        barrier = Barrier(2)

        def worker(index):
            barrier.wait(timeout=15)
            return self._import_worker(f"synthetic-concurrent-{index}.pdf")

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(worker, range(2)))
        self.assertCountEqual(statuses, [ImportBatch.Status.ACCEPTED, ImportBatch.Status.DUPLICATE])
        self.assertEqual(FinancialObservation.objects.count(), 1)
        self.assertEqual(Movement.objects.count(), 0)
        batch = ImportBatch.objects.get(status=ImportBatch.Status.ACCEPTED)
        self.assertEqual(len(resolve_bci_historical_batch(import_batch_id=batch.pk)), 1)
        self.assertEqual(Movement.objects.count(), 1)

    def test_concurrent_historical_resolution_is_idempotent(self):
        batch = self._import_worker("synthetic-resolution.pdf")
        observation = FinancialObservation.objects.get()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                result = resolve_bci_historical_observation(observation_id=observation.pk)
                return result is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(results), 2)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(ObservationResolution.objects.count(), 1)
        self.assertEqual(FinancialObservation.objects.get().state, FinancialObservation.State.RESOLVED)

    def test_concurrent_same_statement_identical_rows_both_resolve(self):
        content = synthetic_bci_historical_pdf(rows=(
            {"date": date(2026, 1, 2), "debit": 1000, "reference": "same"},
            {"date": date(2026, 1, 2), "debit": 1000, "reference": "same"},
        ))
        expected = parse_bci_historical_pdf(content).metadata.source_account_id
        batch = import_bci_historical_current_account_pdf(
            content=content,
            original_filename="synthetic-same-statement.pdf",
            account=self.account,
            expected_source_account_id=expected,
        )
        observations = list(FinancialObservation.objects.filter(raw_record__import_batch=batch).order_by("raw_record__record_ordinal"))
        barrier = Barrier(2)

        def worker(observation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return resolve_bci_historical_observation(observation_id=observation.pk) is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, observations))
        self.assertEqual(results, [True, True])
        self.assertEqual(Movement.objects.count(), 2)
        self.assertEqual(FinancialObservation.objects.filter(state=FinancialObservation.State.RESOLVED).count(), 2)

    def test_concurrent_same_statement_rows_abstain_with_external_candidate(self):
        external = self._import_worker("synthetic-external-preexisting.pdf")
        external_observation = FinancialObservation.objects.get()
        self.assertIsNotNone(resolve_bci_historical_observation(observation_id=external_observation.pk))
        target_content = synthetic_bci_historical_pdf(
            rows=(
                {"date": date(2026, 1, 2), "debit": 1000},
                {"date": date(2026, 1, 2), "debit": 1000},
            ),
            source_account_id="900000000002",
        )
        target = import_bci_historical_current_account_pdf(
            content=target_content,
            original_filename="synthetic-external-preexisting-target.pdf",
            account=self.account,
            expected_source_account_id="900000000002",
        )
        observations = list(FinancialObservation.objects.filter(raw_record__import_batch=target).order_by("raw_record__record_ordinal"))
        barrier = Barrier(2)

        def worker(observation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return resolve_bci_historical_observation(observation_id=observation.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, observations))
        self.assertEqual(results, [None, None])
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(FinancialObservation.objects.filter(raw_record__import_batch=target, state=FinancialObservation.State.UNRESOLVED).count(), 2)

    def test_concurrent_external_candidate_appearance_cannot_duplicate_movement(self):
        target = self._import_worker("synthetic-concurrent-target.pdf")
        target_observation = FinancialObservation.objects.get()
        external_content = synthetic_bci_historical_pdf(
            rows=({"date": date(2026, 1, 2), "debit": 1000},),
            source_account_id="900000000002",
        )
        external_batch = import_bci_historical_current_account_pdf(
            content=external_content,
            original_filename="synthetic-concurrent-external.pdf",
            account=self.account,
            expected_source_account_id="900000000002",
        )
        external_observation = FinancialObservation.objects.get(raw_record__import_batch=external_batch)
        barrier = Barrier(2)

        def worker(observation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return resolve_bci_historical_observation(observation_id=observation.pk) is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, (target_observation, external_observation)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(FinancialObservation.objects.filter(state=FinancialObservation.State.RESOLVED).count(), 1)
        self.assertEqual(FinancialObservation.objects.filter(state=FinancialObservation.State.UNRESOLVED).count(), 1)

    def test_concurrent_resolution_abstains_when_external_candidate_commits_first(self):
        external = self._import_worker("synthetic-external.pdf")
        external_observation = FinancialObservation.objects.get()
        self.assertIsNotNone(resolve_bci_historical_observation(observation_id=external_observation.pk))
        target_content = synthetic_bci_historical_pdf(
            rows=(
                {"date": date(2026, 1, 2), "debit": 1000},
                {"date": date(2026, 1, 2), "debit": 1000},
            ),
            source_account_id="900000000002",
        )
        target = import_bci_historical_current_account_pdf(
            content=target_content,
            original_filename="synthetic-external-collision.pdf",
            account=self.account,
            expected_source_account_id="900000000002",
        )
        observations = list(FinancialObservation.objects.filter(raw_record__import_batch=target).order_by("raw_record__record_ordinal"))
        barrier = Barrier(2)

        def worker(observation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return resolve_bci_historical_observation(observation_id=observation.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, observations))
        self.assertEqual(results, [None, None])
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(FinancialObservation.objects.filter(raw_record__import_batch=target, state=FinancialObservation.State.UNRESOLVED).count(), 2)
