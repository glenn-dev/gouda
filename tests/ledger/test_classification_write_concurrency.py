"""Run the existing real PostgreSQL contention scenarios through HTTP."""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import Client

from gouda.local_delivery import run_validated_local_delivery
from gouda.local_classification_write import WRITE_ORIGIN
from gouda.ledger.models import Movement, MovementClassification, RawRecord, ImportBatch, SourceArtifact
from gouda.ledger.services import movement_reporting
from tests.fixtures.local_classification_write import BOOTSTRAP, HEADERS, patch_classification, write_runtime
from tests.ledger import test_movement_classification_concurrency as domain_tests


class ClassificationWriteConcurrencyTests(domain_tests.MovementClassificationConcurrencyTests):
    """Reuse domain fixtures, pg_blocking_pids barriers, and all six races."""

    def in_runtime(self, operation):
        def run(_):
            self.capability = Client().post(BOOTSTRAP, data="{}", content_type="application/json", **HEADERS).json()["write_capability"]
            return operation()
        return run_validated_local_delivery(
            bind_host="127.0.0.1", port="8000", enable_classification_writes=True,
            classification_write_origin=WRITE_ORIGIN, server_runner=run,
        )

    def command(self, category, revision):
        def send():
            response = patch_classification(self.movement, self.capability, category, revision)
            return response.status_code, response.json()
        if getattr(self, "contending", False):
            return send()
        return self.in_runtime(send)

    def contend(self, commands, *, retire=None):
        def run():
            self.contending = True
            try:
                results = super(ClassificationWriteConcurrencyTests, self).contend(commands, retire=retire)
                converted = []
                for kind, (status, body) in results:
                    self.assertEqual(kind, "ok")
                    self.assertIn(status, (200, 409))
                    converted.append(("ok", body["classification"]) if status == 200 else ("error", body["code"]))
                return converted
            finally:
                self.contending = False
        baseline = [list(model.objects.order_by("pk").values()) for model in (Movement, RawRecord, ImportBatch, SourceArtifact)]
        results = self.in_runtime(run)
        self.assertEqual(baseline, [list(model.objects.order_by("pk").values()) for model in (Movement, RawRecord, ImportBatch, SourceArtifact)])
        return results

    def assert_single_winner(self, results, revision):
        self.assertEqual([kind for kind, _ in results].count("ok"), 1)
        self.assertEqual([value for kind, value in results if kind == "error"], ["classification_revision_conflict"])
        winner = next(value for kind, value in results if kind == "ok")
        row = MovementClassification.objects.get()
        self.assertEqual(row.revision, revision)
        self.assertEqual(winner["revision"], revision)
        self.assertEqual(winner["category"]["id"] if winner["category"] else None,
                         str(row.category_id) if row.category_id else None)
        self.assertEqual(set(winner), {"state", "category", "revision"})

    @write_runtime
    def test_projection_holds_locks_and_returns_own_revision_before_next_writer(self):
        projected = Event()
        release = Event()
        pids = Queue()
        original = movement_reporting.project_movement_classification

        def held_projection(current):
            value = original(current)
            if value.revision == 1:
                projected.set()
                if not release.wait(8):
                    raise RuntimeError("synthetic projection wait expired")
            return value

        def worker(category, revision):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
                response = patch_classification(self.movement, self.capability, category, revision)
                return response.status_code, response.json()
            finally:
                connection.close()

        with patch.object(movement_reporting, "project_movement_classification", side_effect=held_projection), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker, self.categories[0], 0)
            pids.get(timeout=8)
            try:
                self.assertTrue(projected.wait(8))
                second = pool.submit(worker, self.categories[1], 1)
                second_pid = pids.get(timeout=8)
                deadline = monotonic() + 8
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [second_pid])
                        if cursor.fetchone()[0] > 0:
                            break
                    self.assertLess(monotonic(), deadline, "second writer must wait during projection")
                    sleep(0.01)
            finally:
                release.set()
            first_status, first_body = first.result(timeout=10)
            second_status, second_body = second.result(timeout=10)
        self.assertEqual((first_status, second_status), (200, 200))
        self.assertEqual(first_body["classification"]["revision"], 1)
        self.assertEqual(first_body["classification"]["category"]["id"], str(self.categories[0].pk))
        self.assertEqual(second_body["classification"]["revision"], 2)
        self.assertEqual(MovementClassification.objects.get().category_id, self.categories[1].pk)

    @write_runtime
    def test_projection_failure_rolls_back_real_transaction_and_next_writer_can_succeed(self):
        with patch.object(movement_reporting, "project_movement_classification", side_effect=RuntimeError("synthetic")):
            response = patch_classification(self.movement, self.capability, self.categories[0], 0)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"code": "internal_error"})
        self.assertFalse(MovementClassification.objects.exists())
        response = patch_classification(self.movement, self.capability, self.categories[1], 0)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"]["revision"], 1)
