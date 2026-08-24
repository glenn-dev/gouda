from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, current_thread
from time import monotonic
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gouda.ledger.models import Account, ImportBatch, Movement, RawRecord, SourceArtifact
from gouda.ledger.services import santander_import as service
from gouda.santander_parser import PARSER_VERSION, parse_workbook
from tests.test_santander_parser import workbook_bytes


_WAIT_SECONDS = 15


class _SelectForUpdateProbe:
    """Observe real Account row-lock acquisition without changing the query."""

    def __init__(self, queryset, *, attempt_barrier, acquired):
        self.queryset = queryset
        self.attempt_barrier = attempt_barrier
        self.acquired = acquired

    def get(self, *args, **kwargs):
        self.attempt_barrier.wait(timeout=_WAIT_SECONDS)
        account = self.queryset.get(*args, **kwargs)
        self.acquired()
        return account


class SantanderImportConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic concurrent current account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        self.content = workbook_bytes(
            opening="$10.00",
            ending="$11.00",
            rows=[
                ["04/02", "cargo", "Synthetic concurrent debit", "SYN-CD", "$1.00", None, "$9.00"],
                ["05/02", "abono", "Synthetic concurrent credit", "SYN-CC", None, "$2.00", "$11.00"],
            ],
        )

    def _worker(self, *, content, account_id, filename):
        close_old_connections()
        try:
            account = Account.objects.get(pk=account_id)
            return service.import_santander_current_account_xlsx(
                content=content,
                original_filename=filename,
                account=account,
            )
        finally:
            close_old_connections()

    def _wait_until_backend_is_blocked_by(self, *, blocked_pid, blocking_pid):
        deadline = monotonic() + 5
        with connection.cursor() as cursor:
            while monotonic() < deadline:
                cursor.execute(
                    "SELECT %s = ANY(pg_blocking_pids(%s))",
                    [blocking_pid, blocked_pid],
                )
                if cursor.fetchone()[0]:
                    return True
        return False

    def test_identical_imports_parse_concurrently_then_serialize_on_account_lock(self):
        real_parse = service.parse_workbook
        real_find = service._find_materialized_batch
        real_select_for_update = Account.objects.select_for_update
        parse_entry = Barrier(2)
        parse_complete = Barrier(2)
        account_lock_attempt = Barrier(2)
        first_account_lock_acquired = Event()
        release_first_account_lock = Event()
        second_account_lock_acquired = Event()
        state_lock = Lock()
        active_parsers = 0
        maximum_active_parsers = 0
        backend_pids_by_thread = {}
        registration_snapshots = []
        find_calls_by_thread = defaultdict(int)
        post_parse_targets = []
        lock_acquisition_count = 0
        first_lock_holder_thread_id = None

        def synchronized_parse(*args, **kwargs):
            nonlocal active_parsers, maximum_active_parsers
            if connection.in_atomic_block:
                raise AssertionError("parser entered with an open database transaction")
            with state_lock:
                active_parsers += 1
                maximum_active_parsers = max(maximum_active_parsers, active_parsers)
                backend_pids_by_thread[current_thread().ident] = connection.connection.info.backend_pid
            parse_entry.wait(timeout=_WAIT_SECONDS)
            registration_snapshots.append(
                (
                    ImportBatch.objects.filter(
                        account_id=self.account.pk,
                        status=ImportBatch.Status.PROCESSING,
                    ).count(),
                    ImportBatch.objects.filter(
                        account_id=self.account.pk,
                        status__in=(
                            ImportBatch.Status.ACCEPTED,
                            ImportBatch.Status.PARTIAL,
                            ImportBatch.Status.REJECTED,
                        ),
                    ).count(),
                )
            )
            result = real_parse(*args, **kwargs)
            parse_complete.wait(timeout=_WAIT_SECONDS)
            with state_lock:
                active_parsers -= 1
            return result

        def observed_find(*args, **kwargs):
            target = real_find(*args, **kwargs)
            thread_id = current_thread().ident
            with state_lock:
                find_calls_by_thread[thread_id] += 1
                if find_calls_by_thread[thread_id] == 2:
                    post_parse_targets.append(None if target is None else target.pk)
            return target

        def account_lock_acquired():
            nonlocal first_lock_holder_thread_id, lock_acquisition_count
            with state_lock:
                lock_acquisition_count += 1
                acquisition_number = lock_acquisition_count
            if acquisition_number == 1:
                first_lock_holder_thread_id = current_thread().ident
                first_account_lock_acquired.set()
                if not release_first_account_lock.wait(timeout=_WAIT_SECONDS):
                    raise AssertionError("test did not release the first Account lock")
            else:
                second_account_lock_acquired.set()

        def observed_select_for_update(*args, **kwargs):
            return _SelectForUpdateProbe(
                real_select_for_update(*args, **kwargs),
                attempt_barrier=account_lock_attempt,
                acquired=account_lock_acquired,
            )

        with patch.object(service, "parse_workbook", side_effect=synchronized_parse), patch.object(
            service,
            "_find_materialized_batch",
            side_effect=observed_find,
        ), patch.object(
            Account.objects,
            "select_for_update",
            side_effect=observed_select_for_update,
        ), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._worker,
                    content=self.content,
                    account_id=self.account.pk,
                    filename=f"synthetic-concurrent-{index}.xlsx",
                )
                for index in range(2)
            ]
            try:
                self.assertTrue(
                    first_account_lock_acquired.wait(timeout=_WAIT_SECONDS),
                    "neither worker acquired the Account row lock",
                )
                with state_lock:
                    blocking_pid = backend_pids_by_thread[first_lock_holder_thread_id]
                    blocked_pid = next(
                        pid
                        for thread_id, pid in backend_pids_by_thread.items()
                        if thread_id != first_lock_holder_thread_id
                    )
                self.assertTrue(
                    self._wait_until_backend_is_blocked_by(
                        blocked_pid=blocked_pid,
                        blocking_pid=blocking_pid,
                    ),
                    "PostgreSQL did not report the second backend blocked by the Account lock holder",
                )
                self.assertFalse(
                    second_account_lock_acquired.is_set(),
                    "both workers acquired the same Account row lock concurrently",
                )
            finally:
                release_first_account_lock.set()
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertEqual(maximum_active_parsers, 2)
        self.assertEqual(len(set(backend_pids_by_thread.values())), 2)
        self.assertEqual(registration_snapshots, [(2, 0), (2, 0)])
        self.assertTrue(second_account_lock_acquired.is_set())
        self.assertEqual(lock_acquisition_count, 2)
        self.assertEqual(len(post_parse_targets), 2)
        self.assertEqual(sum(target is None for target in post_parse_targets), 1)
        self.assertEqual(sum(target is not None for target in post_parse_targets), 1)

        artifact = SourceArtifact.objects.get()
        self.assertEqual(bytes(artifact.content), self.content)
        batches = list(ImportBatch.objects.filter(source_artifact=artifact, account=self.account))
        canonical = [batch for batch in batches if batch.status in service._MATERIALIZED_STATUSES]
        duplicates = [batch for batch in batches if batch.status == ImportBatch.Status.DUPLICATE]
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(len(duplicates), 1)
        self.assertFalse(any(batch.status == ImportBatch.Status.FATAL for batch in batches))
        self.assertFalse(any(batch.status == ImportBatch.Status.PROCESSING for batch in batches))

        winner = canonical[0]
        loser = duplicates[0]
        expected = parse_workbook(
            self.content,
            currency=self.account.currency,
            account_ref=str(self.account.pk),
        )
        self.assertEqual(loser.duplicate_of_id, winner.pk)
        self.assertEqual(loser.source_variant, winner.source_variant)
        self.assertEqual(loser.parser_version, PARSER_VERSION)
        self.assertEqual((loser.parsed_count, loser.ignored_count, loser.rejected_count), (0, 0, 0))
        self.assertIsNone(loser.sheet_alias)
        self.assertIsNone(loser.worksheet_name)
        self.assertIsNone(loser.worksheet_ordinal)
        self.assertIsNone(loser.period_start)
        self.assertIsNone(loser.period_end)
        self.assertIsNone(loser.reconciliation_status)
        self.assertIsNone(loser.opening_balance)
        self.assertIsNone(loser.ending_balance)
        self.assertIsNone(loser.reconciliation_difference)
        self.assertIsNone(loser.failure_stage)
        self.assertIsNone(loser.failure_code)
        self.assertEqual(
            (winner.parsed_count, winner.ignored_count, winner.rejected_count),
            (expected.parsed_count, expected.ignored_count, expected.rejected_count),
        )

        winner_raw_count = RawRecord.objects.filter(import_batch=winner).count()
        winner_movement_count = Movement.objects.filter(raw_record__import_batch=winner).count()
        self.assertEqual(winner_raw_count, len(expected.rows))
        self.assertEqual(winner_movement_count, expected.parsed_count)
        self.assertFalse(RawRecord.objects.filter(import_batch=loser).exists())
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=loser).exists())
        self.assertEqual(RawRecord.objects.count(), len(expected.rows))
        self.assertEqual(Movement.objects.count(), expected.parsed_count)

        durable_results = [ImportBatch.objects.get(pk=result.pk) for result in results]
        self.assertEqual(
            {result.status for result in durable_results},
            {winner.status, ImportBatch.Status.DUPLICATE},
        )

    def test_different_artifacts_same_account_parse_together_and_materialize_serially(self):
        other_content = workbook_bytes(
            sheet_name="Second synthetic statement",
            opening="$20.00",
            ending="$19.00",
            rows=[
                ["06/02", "cargo", "Second synthetic debit", "SYN-SECOND", "$1.00", None, "$19.00"],
            ],
        )
        real_parse = service.parse_workbook
        real_select_for_update = Account.objects.select_for_update
        parse_entry = Barrier(2)
        parse_complete = Barrier(2)
        account_lock_attempt = Barrier(2)
        first_acquired = Event()
        release_first = Event()
        second_acquired = Event()
        state_lock = Lock()
        acquisition_count = 0
        active_parsers = 0
        maximum_active_parsers = 0

        def synchronized_parse(*args, **kwargs):
            nonlocal active_parsers, maximum_active_parsers
            if connection.in_atomic_block:
                raise AssertionError("parser entered with an open database transaction")
            with state_lock:
                active_parsers += 1
                maximum_active_parsers = max(maximum_active_parsers, active_parsers)
            parse_entry.wait(timeout=_WAIT_SECONDS)
            result = real_parse(*args, **kwargs)
            parse_complete.wait(timeout=_WAIT_SECONDS)
            with state_lock:
                active_parsers -= 1
            return result

        def acquired():
            nonlocal acquisition_count
            with state_lock:
                acquisition_count += 1
                number = acquisition_count
            if number == 1:
                first_acquired.set()
                if not release_first.wait(timeout=_WAIT_SECONDS):
                    raise AssertionError("test did not release the first Account lock")
            else:
                second_acquired.set()

        def observed_select_for_update(*args, **kwargs):
            return _SelectForUpdateProbe(
                real_select_for_update(*args, **kwargs),
                attempt_barrier=account_lock_attempt,
                acquired=acquired,
            )

        with patch.object(service, "parse_workbook", side_effect=synchronized_parse), patch.object(
            Account.objects,
            "select_for_update",
            side_effect=observed_select_for_update,
        ), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._worker,
                    content=content,
                    account_id=self.account.pk,
                    filename=f"different-artifact-{index}.xlsx",
                )
                for index, content in enumerate((self.content, other_content))
            ]
            try:
                self.assertTrue(first_acquired.wait(timeout=_WAIT_SECONDS))
                self.assertFalse(second_acquired.is_set())
            finally:
                release_first.set()
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertEqual(maximum_active_parsers, 2)
        self.assertTrue(second_acquired.is_set())
        self.assertEqual(SourceArtifact.objects.count(), 2)
        self.assertEqual(ImportBatch.objects.filter(status=ImportBatch.Status.ACCEPTED).count(), 2)
        self.assertFalse(ImportBatch.objects.filter(status=ImportBatch.Status.DUPLICATE).exists())
        self.assertFalse(ImportBatch.objects.filter(status=ImportBatch.Status.FATAL).exists())
        self.assertEqual({ImportBatch.objects.get(pk=result.pk).status for result in results}, {ImportBatch.Status.ACCEPTED})

    def test_different_accounts_hold_their_account_locks_concurrently(self):
        other_account = Account.objects.create(
            display_name="Other synthetic concurrent account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        real_parse = service.parse_workbook
        real_select_for_update = Account.objects.select_for_update
        parse_barrier = Barrier(2)
        both_account_locks_acquired = Barrier(2)
        state_lock = Lock()
        backend_pids = set()
        locked_account_ids = set()

        def synchronized_parse(*args, **kwargs):
            if connection.in_atomic_block:
                raise AssertionError("parser entered with an open database transaction")
            with state_lock:
                backend_pids.add(connection.connection.info.backend_pid)
            parse_barrier.wait(timeout=_WAIT_SECONDS)
            return real_parse(*args, **kwargs)

        class DifferentAccountProbe:
            def __init__(self, queryset):
                self.queryset = queryset

            def get(probe_self, *args, **kwargs):
                account = probe_self.queryset.get(*args, **kwargs)
                with state_lock:
                    locked_account_ids.add(account.pk)
                both_account_locks_acquired.wait(timeout=_WAIT_SECONDS)
                return account

        def observed_select_for_update(*args, **kwargs):
            return DifferentAccountProbe(real_select_for_update(*args, **kwargs))

        with patch.object(service, "parse_workbook", side_effect=synchronized_parse), patch.object(
            Account.objects,
            "select_for_update",
            side_effect=observed_select_for_update,
        ), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._worker,
                    content=self.content,
                    account_id=account_id,
                    filename=f"different-account-{index}.xlsx",
                )
                for index, account_id in enumerate((self.account.pk, other_account.pk))
            ]
            results = [future.result(timeout=_WAIT_SECONDS) for future in futures]

        self.assertEqual(len(backend_pids), 2)
        self.assertEqual(locked_account_ids, {self.account.pk, other_account.pk})
        self.assertEqual(SourceArtifact.objects.count(), 1)
        self.assertEqual(ImportBatch.objects.filter(status=ImportBatch.Status.ACCEPTED).count(), 2)
        self.assertFalse(ImportBatch.objects.filter(status=ImportBatch.Status.DUPLICATE).exists())
        self.assertEqual({ImportBatch.objects.get(pk=result.pk).status for result in results}, {ImportBatch.Status.ACCEPTED})
