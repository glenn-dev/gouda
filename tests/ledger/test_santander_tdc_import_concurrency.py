from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gouda.ledger.models import (
    Account,
    ImportBatch,
    Movement,
    SantanderTdcAccountBinding,
)
from gouda.ledger.services import santander_tdc_import as service
from tests.ledger.test_santander_tdc_evidence import synthetic_result


_WAIT_SECONDS = 15


class _SelectForUpdateProbe:
    def __init__(self, queryset, *, attempt_barrier, acquired):
        self.queryset = queryset
        self.attempt_barrier = attempt_barrier
        self.acquired = acquired

    def get(self, *args, **kwargs):
        self.attempt_barrier.wait(timeout=_WAIT_SECONDS)
        account = self.queryset.get(*args, **kwargs)
        self.acquired()
        return account


class SantanderTdcImportConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.account = self.make_account("Primary")
        service.configure_santander_tdc_account_binding(
            account=self.account,
            card_last_four="0079",
        )

    def make_account(self, suffix):
        return Account.objects.create(
            display_name=f"Synthetic concurrent card {suffix}",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )

    def worker(self, *, account_id, content, filename):
        close_old_connections()
        try:
            account = Account.objects.get(pk=account_id)
            return service.import_santander_credit_card_pdf(
                content=content,
                original_filename=filename,
                account=account,
            )
        finally:
            close_old_connections()

    def test_same_artifact_account_and_route_has_one_canonical_and_one_duplicate(self):
        parse_barrier = Barrier(2)

        def synchronized_parse(_content):
            self.assertFalse(connection.in_atomic_block)
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return synthetic_result()

        content = b"synthetic concurrent identical TDC"
        with patch.object(service, "parse_tdc_pdf", side_effect=synchronized_parse), ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [
                executor.submit(
                    self.worker,
                    account_id=self.account.pk,
                    content=content,
                    filename=f"synthetic-{index}.pdf",
                )
                for index in range(2)
            ]
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        canonical = [batch for batch in results if batch.status in service._MATERIALIZED_STATUSES]
        duplicates = [batch for batch in results if batch.status == ImportBatch.Status.DUPLICATE]
        self.assertEqual((len(canonical), len(duplicates)), (1, 1))
        self.assertEqual(duplicates[0].duplicate_of_id, canonical[0].pk)
        self.assertEqual(canonical[0].raw_records.count(), 3)
        self.assertEqual(
            Movement.objects.filter(raw_record__import_batch=canonical[0]).count(),
            1,
        )
        self.assertFalse(duplicates[0].raw_records.exists())
        self.assertEqual(
            ImportBatch.objects.filter(
                account=self.account,
                status=ImportBatch.Status.PROCESSING,
            ).count(),
            0,
        )

    def test_different_artifacts_same_account_parse_together_and_both_materialize(self):
        parse_barrier = Barrier(2)
        account_lock_attempt = Barrier(2)
        first_lock_acquired = Event()
        release_first_lock = Event()
        second_lock_acquired = Event()
        state_lock = Lock()
        acquisition_count = 0
        real_select_for_update = Account.objects.select_for_update

        def synchronized_parse(_content):
            self.assertFalse(connection.in_atomic_block)
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return synthetic_result()

        def acquired():
            nonlocal acquisition_count
            with state_lock:
                acquisition_count += 1
                acquisition_number = acquisition_count
            if acquisition_number == 1:
                first_lock_acquired.set()
                if not release_first_lock.wait(timeout=_WAIT_SECONDS):
                    raise AssertionError("test did not release the first Account lock")
            else:
                second_lock_acquired.set()

        def observed_select_for_update(*args, **kwargs):
            return _SelectForUpdateProbe(
                real_select_for_update(*args, **kwargs),
                attempt_barrier=account_lock_attempt,
                acquired=acquired,
            )

        with patch.object(
            service,
            "parse_tdc_pdf",
            side_effect=synchronized_parse,
        ), patch.object(
            Account.objects,
            "select_for_update",
            side_effect=observed_select_for_update,
        ), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self.worker,
                    account_id=self.account.pk,
                    content=f"synthetic-different-{index}".encode(),
                    filename=f"synthetic-{index}.pdf",
                )
                for index in range(2)
            ]
            try:
                self.assertTrue(first_lock_acquired.wait(timeout=_WAIT_SECONDS))
                self.assertFalse(second_lock_acquired.is_set())
            finally:
                release_first_lock.set()
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertTrue(all(batch.status == ImportBatch.Status.PARTIAL for batch in results))
        self.assertTrue(second_lock_acquired.is_set())
        self.assertEqual(acquisition_count, 2)
        self.assertEqual(len({batch.source_artifact_id for batch in results}), 2)
        self.assertEqual(
            Movement.objects.filter(raw_record__import_batch__in=results).count(),
            2,
        )

    def test_same_artifact_different_explicitly_bound_accounts_can_materialize(self):
        other = self.make_account("Other")
        service.configure_santander_tdc_account_binding(
            account=other,
            card_last_four="0079",
        )
        parse_barrier = Barrier(2)

        def synchronized_parse(_content):
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return synthetic_result()

        content = b"synthetic shared artifact same suffix"
        with patch.object(service, "parse_tdc_pdf", side_effect=synchronized_parse), ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [
                executor.submit(
                    self.worker,
                    account_id=account.pk,
                    content=content,
                    filename="synthetic.pdf",
                )
                for account in (self.account, other)
            ]
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertTrue(all(batch.status == ImportBatch.Status.PARTIAL for batch in results))
        self.assertEqual(len({batch.account_id for batch in results}), 2)
        self.assertEqual(len({batch.source_artifact_id for batch in results}), 1)

    def test_same_artifact_different_suffix_bindings_rejects_wrong_account(self):
        other = self.make_account("Wrong suffix")
        service.configure_santander_tdc_account_binding(
            account=other,
            card_last_four="0080",
        )
        parse_barrier = Barrier(2)

        def synchronized_parse(_content):
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return synthetic_result()

        content = b"synthetic shared artifact different suffix"
        with patch.object(service, "parse_tdc_pdf", side_effect=synchronized_parse), ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [
                executor.submit(
                    self.worker,
                    account_id=account.pk,
                    content=content,
                    filename="synthetic.pdf",
                )
                for account in (self.account, other)
            ]
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertEqual(sum(batch.status == ImportBatch.Status.PARTIAL for batch in results), 1)
        failed = next(batch for batch in results if batch.status == ImportBatch.Status.FATAL)
        self.assertEqual(failed.failure_stage, ImportBatch.FailureStage.BOUNDARY)
        self.assertEqual(failed.failure_code, service.CARD_BINDING_MISMATCH)
        self.assertFalse(failed.raw_records.exists())

    def test_different_artifacts_and_accounts_parse_without_shared_lock(self):
        other = self.make_account("Independent")
        service.configure_santander_tdc_account_binding(
            account=other,
            card_last_four="0079",
        )
        parse_barrier = Barrier(2)

        def synchronized_parse(_content):
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return synthetic_result()

        with patch.object(service, "parse_tdc_pdf", side_effect=synchronized_parse), ThreadPoolExecutor(
            max_workers=2
        ) as executor:
            futures = [
                executor.submit(
                    self.worker,
                    account_id=account.pk,
                    content=f"synthetic-independent-{index}".encode(),
                    filename=f"synthetic-{index}.pdf",
                )
                for index, account in enumerate((self.account, other))
            ]
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]
        self.assertTrue(all(batch.status == ImportBatch.Status.PARTIAL for batch in results))
        self.assertEqual(len({batch.account_id for batch in results}), 2)
        self.assertEqual(len({batch.source_artifact_id for batch in results}), 2)

    def test_binding_creation_race_never_overwrites_winner(self):
        account = self.make_account("Binding race")
        start = Barrier(2)

        def bind(card_last_four):
            close_old_connections()
            try:
                local_account = Account.objects.get(pk=account.pk)
                start.wait(timeout=_WAIT_SECONDS)
                try:
                    binding = service.configure_santander_tdc_account_binding(
                        account=local_account,
                        card_last_four=card_last_four,
                    )
                    return ("created", binding.card_last_four)
                except service.SantanderTdcImportServiceError as error:
                    return ("failed", error.code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(bind, ("0079", "0080")))

        self.assertEqual(sum(result[0] == "created" for result in results), 1)
        self.assertEqual(
            [result[1] for result in results if result[0] == "failed"],
            ["account_binding_conflict"],
        )
        binding = SantanderTdcAccountBinding.objects.get(account=account)
        self.assertIn(binding.card_last_four, {"0079", "0080"})
        self.assertEqual(
            SantanderTdcAccountBinding.objects.filter(account=account).count(),
            1,
        )
