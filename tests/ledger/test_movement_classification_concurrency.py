from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier
from time import monotonic, sleep

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from gouda.ledger.models import Account, Category, MovementClassification
from gouda.ledger.services import movement_classification as service
from tests.fixtures.movement_classification import make_movement


class MovementClassificationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")
        self.movement = make_movement()
        self.account = self.movement.account
        self.categories = [Category.objects.create(display_name=name)
                           for name in ("Groceries", "Utilities", "Transport")]

    def command(self, category, revision):
        return service.set_movement_classification(
            account=self.account, movement_id=self.movement.pk,
            category_id=category.pk if category else None, expected_revision=revision,
        )

    def contend(self, commands, *, retire=None):
        """Prove live overlapping PostgreSQL transactions, without timing guesses."""
        barrier = Barrier(len(commands))
        pids = Queue()

        def worker(command):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
                barrier.wait(timeout=10)
                try:
                    return ("ok", command())
                except service.MovementClassificationServiceError as error:
                    return ("error", error.code)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(commands)) as pool:
            with transaction.atomic():
                if retire is None:
                    Account.objects.select_for_update().get(pk=self.account.pk)
                else:
                    category = Category.objects.select_for_update().get(pk=retire.pk)
                    category.is_active = False
                    category.save(update_fields=["is_active"])
                futures = [pool.submit(worker, command) for command in commands]
                worker_pids = [pids.get(timeout=10) for _ in commands]
                deadline = monotonic() + 8
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE pid = ANY(%s) AND cardinality(pg_blocking_pids(pid)) > 0",
                            [worker_pids],
                        )
                        if cursor.fetchone()[0] == len(commands):
                            break
                    if monotonic() >= deadline:
                        self.fail("All classification writers must overlap on database locks")
                    sleep(0.01)
            return [future.result(timeout=15) for future in futures]

    def assert_single_winner(self, results, revision):
        self.assertEqual([kind for kind, _ in results].count("ok"), 1)
        self.assertEqual([value for kind, value in results if kind == "error"],
                         ["classification_revision_conflict"])
        winner = next(value for kind, value in results if kind == "ok")
        row = MovementClassification.objects.get()
        self.assertEqual(row.pk, self.movement.pk)
        self.assertEqual(row.revision, revision)
        self.assertEqual(row.category_id, winner.category_id)
        self.assertEqual(row.updated_at, winner.updated_at)

    def test_concurrent_initial_assignments_have_one_winner(self):
        results = self.contend([lambda category=category: self.command(category, 0)
                                for category in self.categories[:2]])
        self.assert_single_winner(results, 1)

    def test_competing_updates_with_same_revision_have_one_winner(self):
        self.command(self.categories[0], 0)
        results = self.contend([lambda category=category: self.command(category, 1)
                                for category in self.categories[1:]])
        self.assert_single_winner(results, 2)

    def test_identical_initial_assignments_still_require_revision_match(self):
        results = self.contend([lambda: self.command(self.categories[0], 0)] * 2)
        self.assert_single_winner(results, 1)

    def test_clear_change_race_cannot_lose_a_write(self):
        self.command(self.categories[0], 0)
        results = self.contend([lambda: self.command(None, 1),
                                lambda: self.command(self.categories[1], 1)])
        self.assert_single_winner(results, 2)

    def test_reassign_after_clear_race_reuses_row(self):
        self.command(self.categories[0], 0)
        self.command(None, 1)
        results = self.contend([lambda category=category: self.command(category, 2)
                                for category in self.categories[:2]])
        self.assert_single_winner(results, 3)

    def test_retirement_lock_is_revalidated_before_new_assignment(self):
        category = self.categories[0]
        results = self.contend([lambda: self.command(category, 0)], retire=category)
        self.assertEqual(results, [("error", "category_inactive")])
        self.assertFalse(MovementClassification.objects.exists())
