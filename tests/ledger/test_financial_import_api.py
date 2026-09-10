import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import warnings
import threading
from django.db import close_old_connections, connections

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, RequestFactory, TransactionTestCase

from gouda import local_classification_write
from gouda.local_delivery import run_validated_local_delivery
from gouda.local_financial_import import IMPORT_HOST, IMPORT_ORIGIN, PRIVATE_DATABASE_NAME
from gouda.local_financial_import import require_financial_import_runtime
from gouda.ledger.demo_data import DEMO_ACCOUNT_IDS
from gouda.ledger.models import Account, ImportBatch, Movement, RawRecord, SourceArtifact
from gouda.ledger.services import financial_import_access, santander_import
from gouda.ledger.financial_import_api import (
    MAX_MULTIPART_BYTES,
    MAX_STATEMENT_BYTES,
    SantanderCurrentAccountImportView,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "santander" / "synthetic-current-account.xlsx"
BOOTSTRAP = "/api/v1/local/financial-import-capability/"
HEADERS = {"HTTP_HOST": IMPORT_HOST, "HTTP_ORIGIN": IMPORT_ORIGIN, "HTTP_ACCEPT": "application/json"}


class FinancialImportApiTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic private current Account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        self.content = FIXTURE.read_bytes()

    def run_import_runtime(self, operation, *, classification=False):
        def run(delivery):
            bootstrap = Client().post(
                BOOTSTRAP,
                data="{}",
                content_type="application/json",
                **HEADERS,
            )
            self.assertEqual(bootstrap.status_code, 200)
            self.capability = bootstrap.json()["import_capability"]
            self.delivery = delivery
            return operation()

        with patch.dict(settings.DATABASES["default"], {"NAME": PRIVATE_DATABASE_NAME}):
            return run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="8000",
                enable_classification_writes=classification,
                classification_write_origin=(
                    local_classification_write.WRITE_ORIGIN if classification else None
                ),
                enable_financial_imports=True,
                financial_import_origin=IMPORT_ORIGIN,
                server_runner=run,
            )

    def path(self, account_id=None):
        return f"/api/v1/accounts/{account_id or self.account.pk}/imports/santander-current-account-xlsx/"

    def request(self, *, content=None, filename="synthetic-private.xlsx", data=None, headers=None, path=None):
        statement = SimpleUploadedFile(
            filename,
            self.content if content is None else content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        request_headers = {**HEADERS, "HTTP_X_GOUDA_FINANCIAL_IMPORT": self.capability}
        request_headers.update(headers or {})
        return Client().post(
            path or self.path(),
            data={"statement": statement} if data is None else data,
            **request_headers,
        )

    def assert_error(self, response, code, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(json.loads(response.content), {"code": code})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertFalse(response.cookies)

    def test_inactive_disabled_host_method_origin_and_capability_gates_are_early(self):
        with self.assertNumQueries(0):
            response = Client().post(self.path(), data=b"private", content_type="text/plain", **HEADERS)
        self.assert_error(response, "local_delivery_not_active", 503)

        def read_only(_delivery):
            with self.assertNumQueries(0):
                response = Client().post(self.path(), data=b"private", content_type="text/plain", **HEADERS)
            self.assert_error(response, "financial_import_not_enabled", 403)

        run_validated_local_delivery(
            bind_host="127.0.0.1", port="8000", server_runner=read_only
        )

        def assertions():
            cases = (
                ({"HTTP_HOST": "evil.invalid"}, "host_not_allowed", 400),
                ({"HTTP_ORIGIN": None}, "origin_not_allowed", 403),
                ({"HTTP_ORIGIN": "null"}, "origin_not_allowed", 403),
                ({"HTTP_ORIGIN": IMPORT_ORIGIN + "," + IMPORT_ORIGIN}, "origin_not_allowed", 403),
                ({"HTTP_X_GOUDA_FINANCIAL_IMPORT": None}, "import_capability_invalid", 403),
                ({"HTTP_X_GOUDA_FINANCIAL_IMPORT": "0" * 64}, "import_capability_invalid", 403),
                ({"HTTP_X_GOUDA_FINANCIAL_IMPORT": self.capability + "," + self.capability}, "import_capability_invalid", 403),
            )
            for headers, code, status in cases:
                with self.subTest(code=code), self.assertNumQueries(0):
                    self.assert_error(self.request(headers=headers), code, status)
            with self.assertNumQueries(0):
                response = Client().get(self.path(), **HEADERS)
            self.assert_error(response, "method_not_allowed", 405)
            self.assertEqual(response["Allow"], "POST")

        self.run_import_runtime(assertions)

    def test_bootstrap_is_strict_zero_query_and_exposes_only_import_capability(self):
        def assertions():
            response = Client().post(
                BOOTSTRAP, data="{}", content_type="application/json", **HEADERS
            )
            self.assertEqual(response.json(), {"import_capability": self.capability})
            self.assertNotIn("write_capability", response.json())
            for method in ("get", "put", "patch", "delete", "options", "head"):
                with self.assertNumQueries(0):
                    response = getattr(Client(), method)(BOOTSTRAP, **HEADERS)
                self.assertEqual(response.status_code, 405)

        self.run_import_runtime(assertions)

    def test_classification_capability_cannot_authorize_import(self):
        def assertions():
            classification_response = Client().post(
                "/api/v1/local/classification-write-capability/",
                data="{}",
                content_type="application/json",
                **HEADERS,
            )
            classification_capability = classification_response.json()["write_capability"]
            with self.assertNumQueries(0):
                response = self.request(
                    headers={"HTTP_X_GOUDA_FINANCIAL_IMPORT": classification_capability}
                )
            self.assert_error(response, "import_capability_invalid", 403)

        self.run_import_runtime(assertions, classification=True)

    def test_account_uuid_and_read_principal_do_not_replace_live_import_grant(self):
        def assertions():
            principal = self.delivery.trusted_principal_context()
            runtime = require_financial_import_runtime()
            grant = runtime.verify_capability(self.capability)
            for context, authority, code in (
                (object(), grant, "principal_context_invalid"),
                (principal, object(), "import_capability_invalid"),
            ):
                with self.subTest(code=code), self.assertNumQueries(0), self.assertRaisesMessage(
                    ValueError, code
                ):
                    financial_import_access.import_authorized_santander_current_account_xlsx(
                        principal_context=context,
                        import_grant=authority,
                        account_selector=self.account.pk,
                        admitted_statement_loader=lambda: self.fail("body loader ran"),
                        upload_slot=runtime.acquire_upload_slot,
                    )

        self.run_import_runtime(assertions)

    def test_process_upload_slot_is_nonblocking_and_leaves_no_evidence(self):
        def assertions():
            runtime = require_financial_import_runtime()
            runtime._upload_slot.acquire()
            try:
                self.assert_error(self.request(), "import_busy", 429)
            finally:
                runtime._upload_slot.release()
            self.assertFalse(SourceArtifact.objects.exists())

        self.run_import_runtime(assertions)

    def test_account_resolution_and_compatibility_precede_body_processing(self):
        card = Account.objects.create(
            display_name="Synthetic card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        demo = Account.objects.create(
            id=next(iter(DEMO_ACCOUNT_IDS)),
            display_name="Synthetic reserved demo Account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )

        def assertions():
            self.assert_error(self.request(path=self.path(uuid4())), "account_not_accessible", 404)
            for account in (card, demo):
                self.assert_error(
                    self.request(content=b"not xlsx", path=self.path(account.pk)),
                    "account_source_incompatible",
                    409,
                )
            self.assertFalse(SourceArtifact.objects.exists())

        self.run_import_runtime(assertions)

    def test_negotiation_query_media_selector_and_declared_size_fail_before_database(self):
        def assertions():
            requests = (
                (self.path() + "?source=santander", {"HTTP_ACCEPT": "application/json"}, "query_parameters_not_allowed", 400),
                (self.path(), {"HTTP_ACCEPT": "text/html"}, "not_acceptable", 406),
                (self.path(), {"HTTP_CONTENT_ENCODING": "gzip"}, "unsupported_media_type", 415),
                (self.path(self.account.pk).replace(str(self.account.pk), str(self.account.pk).upper()), {}, "account_selector_invalid", 400),
            )
            for path, headers, code, status in requests:
                with self.subTest(code=code), self.assertNumQueries(0):
                    response = Client().post(
                        path,
                        data=b"private",
                        content_type="multipart/form-data; boundary=synthetic",
                        **{**HEADERS, **headers},
                        HTTP_X_GOUDA_FINANCIAL_IMPORT=self.capability,
                    )
                self.assert_error(response, code, status)

            request = RequestFactory().post(
                self.path(),
                data=b"",
                content_type="multipart/form-data; boundary=synthetic",
                **HEADERS,
                HTTP_X_GOUDA_FINANCIAL_IMPORT=self.capability,
            )
            request.META["CONTENT_LENGTH"] = str(MAX_MULTIPART_BYTES + 1)
            request.read = lambda _size: self.fail("oversized body was read")
            with self.assertNumQueries(0):
                response = SantanderCurrentAccountImportView.as_view()(
                    request, account_uuid=str(self.account.pk)
                )
            self.assert_error(response, "request_body_too_large", 413)

        self.run_import_runtime(assertions)

    def test_multipart_contract_media_and_size_are_strict(self):
        def assertions():
            self.assert_error(
                Client().post(
                    self.path(),
                    data={},
                    **HEADERS,
                    HTTP_X_GOUDA_FINANCIAL_IMPORT=self.capability,
                ),
                "statement_missing",
                400,
            )
            self.assert_error(
                self.request(data={"statement": SimpleUploadedFile("x.xlsx", self.content), "extra": "x"}),
                "request_body_invalid",
                400,
            )
            self.assert_error(
                self.request(
                    data={
                        "statement": SimpleUploadedFile("x.xlsx", self.content),
                        "statement2": SimpleUploadedFile("y.xlsx", self.content),
                    }
                ),
                "request_body_invalid",
                400,
            )
            self.assert_error(
                self.request(
                    data={
                        "statement": SimpleUploadedFile(
                            "x.xlsx", self.content, content_type="application/pdf"
                        )
                    }
                ),
                "unsupported_media_type",
                415,
            )
            self.assert_error(
                self.request(content=b"x" * (MAX_STATEMENT_BYTES + 1)),
                "statement_too_large",
                413,
            )
            self.assert_error(
                self.request(content=b"x" * MAX_STATEMENT_BYTES), "xlsx_invalid", 422
            )
            self.assertFalse(SourceArtifact.objects.exists())

        self.run_import_runtime(assertions)

    def test_success_reuses_importer_and_returns_bounded_truthful_result(self):
        def assertions():
            def noisy_import(**kwargs):
                warnings.warn("private-cell-sentinel", UserWarning)
                return santander_import.import_santander_current_account_xlsx(**kwargs)

            with warnings.catch_warnings(record=True) as emitted:
                warnings.simplefilter("always")
                with patch.object(
                    financial_import_access,
                    "import_santander_current_account_xlsx",
                    side_effect=noisy_import,
                ) as lower_level:
                    response = self.request(filename="path-marker-private.pdf")
            self.assertEqual(response.status_code, 200)
            lower_level.assert_called_once()
            self.assertEqual(emitted, [])
            body = response.json()
            self.assertEqual(set(body), {
                "account_id", "batch_id", "status", "duplicate_of",
                "created_movement_count", "statement",
            })
            self.assertEqual(body["account_id"], str(self.account.pk))
            self.assertIn(body["status"], {"ACCEPTED", "PARTIAL", "REJECTED"})
            self.assertEqual(body["created_movement_count"], body["statement"]["parsed_count"])
            self.assertEqual(
                body["statement"]["source_row_count"],
                body["statement"]["parsed_count"]
                + body["statement"]["ignored_count"]
                + body["statement"]["rejected_count"],
            )
            response_text = response.content.decode()
            for private in ("path-marker-private.pdf", "content_digest", "source_artifact", "raw_cells"):
                self.assertNotIn(private, response_text)
            self.assertEqual(SourceArtifact.objects.get().original_filename, "path-marker-private.pdf")

        self.run_import_runtime(assertions)

    def test_exact_duplicate_creates_attempt_but_no_new_canonical_movements(self):
        def assertions():
            first = self.request()
            movement_ids = set(Movement.objects.values_list("pk", flat=True))
            duplicate = self.request(filename="different-name.xlsx")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(duplicate.status_code, 200)
            body = duplicate.json()
            self.assertEqual(body["status"], "DUPLICATE")
            self.assertEqual(body["duplicate_of"], first.json()["batch_id"])
            self.assertEqual(body["created_movement_count"], 0)
            self.assertEqual(body["statement"], first.json()["statement"])
            self.assertEqual(set(Movement.objects.values_list("pk", flat=True)), movement_ids)
            self.assertEqual(ImportBatch.objects.filter(status="DUPLICATE").count(), 1)
            self.assertEqual(SourceArtifact.objects.count(), 1)

        self.run_import_runtime(assertions)

    def test_malformed_and_unrecognized_files_have_distinct_evidence_semantics(self):
        def assertions():
            self.assert_error(self.request(content=b"private malformed bytes"), "xlsx_invalid", 422)
            self.assertFalse(SourceArtifact.objects.exists())

            from openpyxl import Workbook
            from io import BytesIO

            workbook = Workbook()
            workbook.active["A1"] = "Synthetic unrelated workbook"
            buffer = BytesIO()
            workbook.save(buffer)
            self.assert_error(self.request(content=buffer.getvalue()), "source_unrecognized", 422)
            self.assertEqual(SourceArtifact.objects.count(), 1)
            batch = ImportBatch.objects.get()
            self.assertEqual(batch.status, ImportBatch.Status.FATAL)
            self.assertFalse(RawRecord.objects.exists())
            self.assertFalse(Movement.objects.exists())

        self.run_import_runtime(assertions)

    def test_materialization_failure_leaves_no_partial_canonical_graph(self):
        def assertions():
            with patch.object(Movement.objects, "create", side_effect=DatabaseError("private sentinel")):
                self.assert_error(self.request(), "import_persistence_failed", 503)
            batch = ImportBatch.objects.get()
            self.assertEqual(batch.status, ImportBatch.Status.FATAL)
            self.assertFalse(RawRecord.objects.exists())
            self.assertFalse(Movement.objects.exists())

        self.run_import_runtime(assertions)

    def test_failures_after_partial_inserts_and_finalization_roll_back_whole_graph(self):
        def assertions():
            for model in (RawRecord, Movement):
                original = model.objects.create
                calls = 0

                def fail_second(**kwargs):
                    nonlocal calls
                    calls += 1
                    result = original(**kwargs)
                    if calls == 2:
                        raise DatabaseError("synthetic-private-database-sentinel")
                    return result

                with self.subTest(model=model.__name__), patch.object(model.objects, "create", side_effect=fail_second):
                    self.assert_error(self.request(), "import_persistence_failed", 503)
                self.assertFalse(RawRecord.objects.exists())
                self.assertFalse(Movement.objects.exists())
            original_finalize = santander_import._finalize_materialized_batch

            def fail_after_finalize(**kwargs):
                original_finalize(**kwargs)
                raise DatabaseError("synthetic-private-finalization-sentinel")

            with patch.object(santander_import, "_finalize_materialized_batch", side_effect=fail_after_finalize):
                self.assert_error(self.request(), "import_persistence_failed", 503)
            self.assertEqual(ImportBatch.objects.filter(status="FATAL").count(), 3)
            self.assertEqual(SourceArtifact.objects.count(), 1)
            self.assertFalse(RawRecord.objects.exists())
            self.assertFalse(Movement.objects.exists())
        self.run_import_runtime(assertions)

    def test_registration_failure_and_postcommit_projection_have_distinct_survival(self):
        def assertions():
            original_create = ImportBatch.objects.create

            def fail_after_attempt(**kwargs):
                original_create(**kwargs)
                raise DatabaseError("synthetic-private-registration-sentinel")

            with patch.object(ImportBatch.objects, "create", side_effect=fail_after_attempt):
                self.assert_error(self.request(), "import_persistence_failed", 503)
            self.assertFalse(SourceArtifact.objects.exists())
            self.assertFalse(ImportBatch.objects.exists())
            with patch("gouda.ledger.financial_import_api._project_result", side_effect=DatabaseError("synthetic-projection")):
                self.assert_error(self.request(), "internal_error", 500)
            original = list(Movement.objects.order_by("pk").values())
            self.assertTrue(original)
            response = self.request()
            self.assertEqual(response.json()["status"], "DUPLICATE")
            self.assertEqual(response.json()["created_movement_count"], 0)
            self.assertEqual(list(Movement.objects.order_by("pk").values()), original)
        self.run_import_runtime(assertions)

    def test_concurrent_http_upload_is_busy_then_explicit_retry_is_duplicate(self):
        entered, release = threading.Event(), threading.Event()
        result = []
        original_parse = santander_import.parse_workbook

        def blocked_parse(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("synthetic test synchronization failed")
            return original_parse(*args, **kwargs)

        def assertions(_delivery):
            self.capability = require_financial_import_runtime().bootstrap_capability()

            def first_request():
                close_old_connections()
                try:
                    result.append(self.request())
                finally:
                    connections.close_all()

            with patch.object(santander_import, "parse_workbook", side_effect=blocked_parse):
                thread = threading.Thread(target=first_request)
                thread.start()
                try:
                    self.assertTrue(entered.wait(5))
                    self.assert_error(self.request(), "import_busy", 429)
                finally:
                    release.set()
                    thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result[0].status_code, 200)
            self.assertEqual(self.request().json()["status"], "DUPLICATE")
            self.assertEqual(ImportBatch.objects.count(), 2)
            self.assertEqual(SourceArtifact.objects.count(), 1)

        # Keep every thread on the isolated test DB while exercising live grants.
        with patch("gouda.local_financial_import.PRIVATE_DATABASE_NAME", settings.DATABASES["default"]["NAME"]):
            run_validated_local_delivery(bind_host="127.0.0.1", port="8000",
                enable_financial_imports=True, financial_import_origin=IMPORT_ORIGIN,
                server_runner=assertions)
