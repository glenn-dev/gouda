import json
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError
from django.test import TestCase, override_settings

from gouda.local_delivery import run_validated_local_delivery
from gouda.local_classification_write import require_classification_write_runtime
from gouda.ledger.models import Category, Movement, MovementClassification
from gouda.ledger.services import account_access, classification_access, movement_classification
from tests.fixtures.movement_classification import make_movement
from tests.fixtures.local_classification_write import (
    BOOTSTRAP, HEADERS, classification_path, patch_classification, write_runtime,
)


class ClassificationWriteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.movement = make_movement()
        cls.other = make_movement(label="other")
        cls.category = Category.objects.create(display_name="Synthetic topic")
        cls.inactive = Category.objects.create(display_name="Retired topic", is_active=False)

    def request(self, *, bootstrap=False, body=None, method=None, headers=None, path=None, query="", **extra):
        request_headers = dict(HEADERS)
        if not bootstrap:
            request_headers["HTTP_X_GOUDA_CLASSIFICATION_WRITE"] = getattr(self, "capability", "0" * 64)
        for key, value in (headers or {}).items():
            if value is None:
                request_headers.pop(key, None)
            else:
                request_headers[key] = value
        if body is None:
            body = "{}" if bootstrap else json.dumps({"category_id": str(self.category.pk), "expected_revision": 0})
        media = extra.pop("content_type", "application/json")
        return self.client.generic(
            method or ("POST" if bootstrap else "PATCH"),
            (path or (BOOTSTRAP if bootstrap else classification_path(self.movement))) + query,
            data=body, content_type=media, CONTENT_TYPE=media,
            **request_headers, **extra,
        )

    def assert_error(self, response, code, status):
        self.assertEqual(response.status_code, status)
        if response.wsgi_request.method != "HEAD":
            self.assertEqual(response.json(), {"code": code})
        self.assert_safety(response)

    def assert_safety(self, response):
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertFalse(response.cookies)
        for header in response.headers:
            self.assertFalse(header.lower().startswith("access-control-"))
        self.assertNotIn("Location", response)

    def test_inactive_and_read_only_runtime_precede_all_request_checks(self):
        for bootstrap in (False, True):
            with self.assertNumQueries(0):
                self.assert_error(self.request(bootstrap=bootstrap, headers={"HTTP_HOST": "evil.invalid"}),
                                  "local_delivery_not_active", 503)
        def read_only(_):
            for bootstrap in (False, True):
                with self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, method="GET", headers={"HTTP_HOST": "evil.invalid"}),
                                      "mutation_not_enabled", 403)
        run_validated_local_delivery(bind_host="127.0.0.1", port="8000", server_runner=read_only)

    @write_runtime
    def test_host_gate_is_exact_and_precedes_method_with_zero_queries(self):
        for value in (None, "", "evil.invalid", "localhost:5173", "127.0.0.1", "127.0.0.1:8000",
                      "127.0.0.1:05173", "127.0.0.1.:5173", "[::1]:5173", "backend:8000",
                      "127.0.0.1:5173,127.0.0.1:5173", "127.0.0.1:5173@evil.invalid"):
            for bootstrap in (False, True):
                with self.subTest(value=value, bootstrap=bootstrap), self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, method="GET", headers={"HTTP_HOST": value}),
                                      "host_not_allowed", 400)

    @write_runtime
    @override_settings(ALLOWED_HOSTS=["*"])
    def test_explicit_host_policy_survives_permissive_django_allowlist(self):
        with self.assertNumQueries(0):
            self.assert_error(self.request(headers={"HTTP_HOST": "evil.invalid", "HTTP_X_FORWARDED_HOST": HEADERS["HTTP_HOST"]}),
                              "host_not_allowed", 400)

    @write_runtime
    def test_origin_gate_rejects_missing_foreign_null_malformed_and_duplicates(self):
        for value in (None, "", "null", "http://evil.invalid", "http://localhost:5173",
                      "http://127.0.0.1", "http://127.0.0.1:8000", "https://127.0.0.1:5173",
                      "http://[::1]:5173", "http://127.0.0.1:5173/", " http://127.0.0.1:5173",
                      "http://127.0.0.1:5173 http://127.0.0.1:5173",
                      "http://127.0.0.1:5173,http://evil.invalid"):
            for bootstrap in (False, True):
                with self.subTest(value=value, bootstrap=bootstrap), self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, headers={
                        "HTTP_ORIGIN": value, "HTTP_REFERER": HEADERS["HTTP_ORIGIN"] + "/",
                        "HTTP_X_FORWARDED_HOST": HEADERS["HTTP_HOST"],
                    }), "origin_not_allowed", 403)

    @write_runtime
    def test_invalid_capabilities_fail_before_body_or_database(self):
        for value in (None, "", "0" * 64, "f" * 63, self.capability.upper(),
                      self.capability + "," + self.capability, " " + self.capability):
            with self.subTest(value=value), self.assertNumQueries(0):
                self.assert_error(self.request(body="invalid", headers={"HTTP_X_GOUDA_CLASSIFICATION_WRITE": value}),
                                  "write_capability_invalid", 403)

    @write_runtime
    def test_body_cookie_authorization_and_query_cannot_supply_capability(self):
        self.client.cookies["write_capability"] = self.capability
        for kwargs in (
            {"query": "?write_capability=" + self.capability},
            {"body": json.dumps({"write_capability": self.capability})},
            {"headers": {"HTTP_AUTHORIZATION": self.capability}},
            {},
        ):
            kwargs.setdefault("headers", {})["HTTP_X_GOUDA_CLASSIFICATION_WRITE"] = None
            with self.assertNumQueries(0):
                self.assert_error(self.request(**kwargs), "write_capability_invalid", 403)

    @write_runtime
    def test_bootstrap_has_only_reusable_capability_and_no_database(self):
        with self.assertNumQueries(0):
            response = self.request(bootstrap=True)
        self.assertEqual(response.json(), {"write_capability": self.capability})
        self.assert_safety(response)

    @write_runtime
    def test_invalid_principal_is_rejected_independently(self):
        with patch.object(account_access, "trusted_local_principal_context", return_value=account_access.TrustedPrincipalContext()):
            for bootstrap in (False, True):
                with self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap), "principal_context_invalid", 403)

    @write_runtime
    def test_methods_precede_origin_and_negotiation(self):
        for bootstrap, allowed in ((False, "PATCH"), (True, "POST")):
            for method in {"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE"} - {allowed}:
                with self.subTest(method=method), self.assertNumQueries(0):
                    response = self.request(bootstrap=bootstrap, method=method,
                                            headers={"HTTP_ORIGIN": None, "HTTP_ACCEPT": "text/html"})
                    self.assert_error(response, "method_not_allowed", 405)
                    self.assertEqual(response["Allow"], allowed)
                    if method == "HEAD":
                        self.assertEqual(response.content, b"")

    @write_runtime
    def test_negotiation_query_media_and_encoding_are_strict(self):
        for bootstrap in (False, True):
            for accept in ("text/html", "application/json;q=0", "application/json;q=0, */*;q=1", "*/*;q=0", "application/json;q=wat"):
                with self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, headers={"HTTP_ACCEPT": accept}), "not_acceptable", 406)
            for query in ("?format=json", "?x=1", "?_method=PATCH", "?write_mode=true"):
                with self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, query=query), "query_parameters_not_allowed", 400)
            for media in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data", "application/json; charset=latin-1", "application/json; x=1", "application/merge-patch+json"):
                with self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, content_type=media), "unsupported_media_type", 415)
            with self.assertNumQueries(0):
                self.assert_error(self.request(bootstrap=bootstrap, headers={"HTTP_CONTENT_ENCODING": "gzip"}), "unsupported_media_type", 415)
        for accept in (None, "*/*", "application/*", "text/html, application/json;q=0.2"):
            self.assertEqual(self.request(bootstrap=True, headers={"HTTP_ACCEPT": accept}, content_type="application/json; charset=utf-8").status_code, 200)

    @write_runtime
    def test_unrelated_accept_parameters_do_not_exclude_json(self):
        for accept in (
            "text/html;level=1, application/json",
            'text/html;profile="synthetic,a;b", application/*',
            "application/json;profile=synthetic, application/json",
            "application/json;profile=synthetic;q=0, */*",
        ):
            with self.subTest(accept=accept), self.assertNumQueries(0):
                response = self.request(bootstrap=True, headers={"HTTP_ACCEPT": accept})
                self.assertEqual(response.status_code, 200)
                self.assert_safety(response)
            response = self.request(
                body='{"category_id":null,"expected_revision":0}',
                headers={"HTTP_ACCEPT": accept},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"classification": {
                "state": "NEVER_ASSIGNED", "category": None, "revision": 0,
            }})
        for accept in (
            'text/html;profile="synthetic,application/json,other"',
            "application/json;profile=synthetic",
            "text/html;level=1, application/json;q=0, */*;q=1",
            "application/json;q=0;, */*;q=1",
        ):
            for bootstrap in (False, True):
                with self.subTest(accept=accept, bootstrap=bootstrap), self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, headers={"HTTP_ACCEPT": accept}),
                                      "not_acceptable", 406)

    @write_runtime
    def test_json_shape_and_size_fail_before_queries(self):
        for bootstrap in (False, True):
            for body in (b"", b"{", b"\xff", b"NaN", b"Infinity", b"{\"a\":NaN}"):
                with self.subTest(body=body), self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, body=body), "malformed_json", 400)
            for body in ("null", "[]", '"text"', "1", '{"a":1,"a":2}', '{"principal":"trusted"}'):
                with self.subTest(body=body), self.assertNumQueries(0):
                    self.assert_error(self.request(bootstrap=bootstrap, body=body), "request_body_invalid", 400)
            with self.assertNumQueries(0):
                self.assert_error(self.request(bootstrap=bootstrap, body=" " * 1023 + "{}"), "request_body_too_large", 413)
        self.assertEqual(self.request(bootstrap=True, body=" " * 1022 + "{}").status_code, 200)
        for body in ("{}", '{"category_id":null}', '{"expected_revision":0}',
                     '{"category_id":null,"expected_revision":0,"source":"MANUAL"}',
                     '{"category_id":null,"category_id":null,"expected_revision":0}'):
            with self.assertNumQueries(0):
                self.assert_error(self.request(body=body), "request_body_invalid", 400)

    @write_runtime
    def test_actual_body_read_is_bounded_even_with_false_length(self):
        from django.test import RequestFactory
        from gouda.ledger.classification_api import ClassificationWriteCapabilityView
        request = RequestFactory().post(BOOTSTRAP, data="{}", content_type="application/json", **HEADERS)
        reads = []
        def read(size):
            reads.append(size)
            return b" " * size
        request.read = read
        request.META["CONTENT_LENGTH"] = "2"
        with self.assertNumQueries(0):
            response = ClassificationWriteCapabilityView.as_view()(request)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(reads, [1025])

    @write_runtime
    def test_selector_and_revision_validation_order(self):
        for value in ("bad", str(uuid4()).upper(), uuid4().hex):
            with self.assertNumQueries(0):
                self.assert_error(self.request(path=f"/api/v1/accounts/{value}/movements/bad/classification/"), "account_selector_invalid", 400)
                self.assert_error(self.request(path=f"/api/v1/accounts/{self.movement.account_id}/movements/{value}/classification/"), "movement_id_invalid", 400)
        for value in ("", "bad", str(uuid4()).upper(), 1, 0.0, True, [], {}):
            with self.assertNumQueries(0):
                self.assert_error(self.request(body=json.dumps({"category_id": value, "expected_revision": False})), "category_id_invalid", 400)
        for value in ('true', 'false', 'null', '"0"', '-1', '0.0', '0e0', '1e0', str(2**63), '[]', '{}'):
            with self.assertNumQueries(0):
                self.assert_error(self.request(body='{"category_id":null,"expected_revision":' + value + '}'), "expected_revision_invalid", 400)

    @write_runtime
    def test_account_authorization_and_movement_scope_precede_category_lookup(self):
        with patch.object(account_access, "_principal_may_read_account", return_value=False), self.assertNumQueries(3):
            # Only SAVEPOINT/ROLLBACK/RELEASE; no SELECT is permitted.
            self.assert_error(self.request(), "account_not_accessible", 404)
        for account in (uuid4(),):
            self.assert_error(self.request(path=f"/api/v1/accounts/{account}/movements/{self.movement.pk}/classification/"), "account_not_accessible", 404)
        for movement in (uuid4(), self.other.pk):
            self.assert_error(self.request(path=f"/api/v1/accounts/{self.movement.account_id}/movements/{movement}/classification/",
                                          body=json.dumps({"category_id": str(uuid4()), "expected_revision": 0})), "movement_not_found", 404)

    @write_runtime
    def test_classified_cleared_absent_and_noop_projections(self):
        baseline = list(Movement.objects.values())
        clear_body = '{"category_id":null,"expected_revision":0}'
        response = self.request(body=clear_body)
        self.assertEqual(response.json(), {"classification": {"state": "NEVER_ASSIGNED", "category": None, "revision": 0}})
        self.assertFalse(MovementClassification.objects.exists())
        response = self.request()
        self.assertEqual(response.json(), {"classification": {"state": "CLASSIFIED", "category": {
            "id": str(self.category.pk), "display_name": self.category.display_name, "is_active": True}, "revision": 1}})
        timestamp = MovementClassification.objects.get().updated_at
        self.category.is_active = False
        self.category.save()
        response = patch_classification(self.movement, self.capability, self.category, 1)
        self.assertFalse(response.json()["classification"]["category"]["is_active"])
        self.assertEqual(MovementClassification.objects.get().updated_at, timestamp)
        self.assert_error(self.request(), "classification_revision_conflict", 409)
        response = patch_classification(self.movement, self.capability, None, 1)
        self.assertEqual(response.json(), {"classification": {"state": "CLEARED", "category": None, "revision": 2}})
        self.assert_safety(response)
        self.assert_error(self.request(body=clear_body), "classification_revision_conflict", 409)
        response = patch_classification(self.movement, self.capability, None, 2)
        self.assertEqual(response.json()["classification"]["revision"], 2)
        self.assertEqual(list(Movement.objects.values()), baseline)

    @write_runtime
    def test_domain_conflicts_and_full_bigint_range(self):
        self.assert_error(patch_classification(self.movement, self.capability, self.category, 1), "classification_not_present", 409)
        self.assert_error(patch_classification(self.movement, self.capability, self.inactive, 0), "category_inactive", 409)
        self.assert_error(self.request(body=json.dumps({"category_id": str(uuid4()), "expected_revision": 0})), "category_not_found", 404)
        self.request()
        for revision in (2**53, 2**63 - 1):
            MovementClassification.objects.filter(pk=self.movement.pk).update(revision=revision)
            response = patch_classification(self.movement, self.capability, self.category, revision)
            self.assertEqual(response.json()["classification"]["revision"], revision)
        self.assert_error(patch_classification(self.movement, self.capability, None, 2**63 - 1), "classification_revision_exhausted", 409)

    @write_runtime
    def test_bigint_increment_is_lossless_above_javascript_safe_range(self):
        self.request()
        MovementClassification.objects.filter(pk=self.movement.pk).update(revision=2**53)
        response = patch_classification(self.movement, self.capability, None, 2**53)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["classification"]["revision"], 2**53 + 1)

    @write_runtime
    def test_failed_projection_preserves_existing_assignment_revision_and_timestamp(self):
        self.request()
        before = list(MovementClassification.objects.values())
        with patch.object(classification_access.movement_reporting, "project_movement_classification", side_effect=RuntimeError("synthetic")):
            self.assert_error(patch_classification(self.movement, self.capability, None, 1), "internal_error", 500)
        self.assertEqual(list(MovementClassification.objects.values()), before)

    @write_runtime
    def test_service_error_mapping_and_unknown_failure_sanitization(self):
        codes = {"account_not_found": ("account_not_accessible", 404),
                 "account_not_persisted": ("internal_error", 500),
                 "synthetic_unmapped": ("internal_error", 500)}
        for code, (expected, status) in codes.items():
            with patch.object(movement_classification, "set_movement_classification",
                              side_effect=movement_classification.MovementClassificationServiceError(code)):
                self.assert_error(self.request(), expected, status)
        with patch.object(movement_classification, "set_movement_classification", side_effect=DatabaseError(self.capability)):
            self.assert_error(self.request(), "internal_error", 500)

    @write_runtime
    def test_projection_failure_rolls_back_and_command_runs_exactly_once(self):
        with patch.object(movement_classification, "set_movement_classification", wraps=movement_classification.set_movement_classification) as command:
            with patch.object(classification_access.movement_reporting, "project_movement_classification", side_effect=RuntimeError(self.capability)):
                self.assert_error(self.request(), "internal_error", 500)
            command.assert_called_once()
        self.assertFalse(MovementClassification.objects.exists())

    @write_runtime
    def test_application_requires_identity_and_live_grant_before_database(self):
        runtime = require_classification_write_runtime()
        principal = self.delivery.trusted_principal_context()
        grant = runtime.verify_capability(self.capability)
        for context, authority, code in ((object(), grant, "principal_context_invalid"), (principal, None, "write_capability_invalid")):
            with self.assertNumQueries(0), self.assertRaises(ValueError) as caught:
                classification_access.classify_authorized_movement(
                    principal_context=context, write_grant=authority,
                    account_selector=self.movement.account_id, movement_id=self.movement.pk,
                    category_id=self.category.pk, expected_revision=0,
                )
            self.assertEqual(str(caught.exception), code)

    @write_runtime
    def test_read_responses_never_contain_capability_and_slashless_paths_do_not_redirect(self):
        for path in ("/api/v1/accounts/", "/api/v1/categories/",
                     f"/api/v1/accounts/{self.movement.account_id}/movements/?start_date=2026-01-01&end_date=2026-01-31"):
            response = self.client.get(path, **HEADERS)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(self.capability.encode(), response.content)
            self.assertNotIn(b"write_capability", response.content)
        response = self.request(bootstrap=True, path=BOOTSTRAP.rstrip("/"))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Location", response)
