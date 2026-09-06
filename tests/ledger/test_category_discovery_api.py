from dataclasses import FrozenInstanceError, asdict
from unittest.mock import patch
from uuid import UUID

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from gouda import local_delivery
from gouda.ledger.models import Category
from gouda.ledger.services import account_access


class CategoryDiscoveryApiTests(TestCase):
    endpoint = "/api/v1/categories/"

    def setUp(self):
        self.client = APIClient()

    def active_request(self, method="get", **kwargs):
        return local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=lambda runtime: getattr(self.client, method)(
                self.endpoint, **kwargs
            ),
        )

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json(), {"code": code})
        self.assertEqual(response["Content-Type"], "application/json")

    def test_active_and_inactive_categories_have_exact_fields_and_stable_order(self):
        last = Category.objects.create(
            id=UUID("00000000-0000-4000-8000-000000000001"),
            display_name="Synthetic Zebra",
        )
        first = Category.objects.create(
            id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            display_name="Synthetic Alpha", is_active=False,
        )
        expected = {"categories": [
            {"id": str(first.pk), "display_name": first.display_name, "is_active": False},
            {"id": str(last.pk), "display_name": last.display_name, "is_active": True},
        ]}
        for _ in range(2):
            with CaptureQueriesContext(connection) as queries:
                response = self.active_request()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertEqual(response.json(), expected)
            self.assertEqual(len(queries), 1)
            # Equal labels cannot persist under the unique-name constraint;
            # verify the UUID tie-breaker without weakening that invariant.
            self.assertIn(
                'ORDER BY "ledger_category"."display_name" ASC, "ledger_category"."id" ASC',
                queries[0]["sql"],
            )

    def test_empty_result_has_no_count_or_pagination_metadata(self):
        with self.assertNumQueries(1):
            response = self.active_request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"categories": []})

    def test_unexpected_queries_fail_before_database_access(self):
        for params in (
            {"search": "Synthetic"}, {"ordering": "id"}, {"is_active": "true"},
            {"page": "1"}, {"category_id": "invalid"}, {"principal": "trusted"},
            {"format": "json"}, [("unexpected", "one"), ("unexpected", "two")],
        ):
            with self.subTest(params=params), self.assertNumQueries(0):
                self.assert_error(self.active_request(data=params), 400,
                                  "query_parameters_not_allowed")

    def test_runtime_gate_precedes_query_validation_and_database_access(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.endpoint, {"unexpected": "value"})
        self.assert_error(response, 503, "local_delivery_not_active")

    def test_request_values_cannot_establish_or_influence_principal_trust(self):
        self.client.cookies["principal"] = "client-value"

        def request():
            return self.client.generic(
                "GET", self.endpoint,
                data=b'{"principal":"client-value","owner":"client-value"}',
                content_type="application/json",
                HTTP_X_GOUDA_PRINCIPAL="client-value",
                HTTP_AUTHORIZATION="Bearer client-value",
                HTTP_HOST="127.0.0.1", REMOTE_ADDR="127.0.0.1",
            )

        with self.assertNumQueries(0):
            self.assert_error(request(), 503, "local_delivery_not_active")
        with patch.object(
            account_access, "trusted_local_principal_context",
            wraps=account_access.trusted_local_principal_context,
        ) as issuer:
            response = local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1", port="8000",
                server_runner=lambda runtime: request(),
            )
        self.assertEqual(response.status_code, 200)
        issuer.assert_called_once_with()

    def test_invalid_injected_principal_fails_before_database_access(self):
        with patch.object(local_delivery.LocalDeliveryRuntime,
                          "trusted_principal_context", return_value=object()):
            with self.assertNumQueries(0):
                response = self.active_request()
        self.assert_error(response, 403, "principal_context_invalid")

    def test_only_get_is_supported_without_any_database_work(self):
        for method in ("post", "put", "patch", "delete", "options", "head"):
            with self.subTest(method=method), self.assertNumQueries(0):
                response = self.active_request(method)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")
                if method == "head":
                    self.assertEqual(response.content, b"")
                else:
                    self.assert_error(response, 405, "method_not_allowed")

    def test_non_json_accept_matches_account_discovery_policy(self):
        for accept in ("text/html", "application/xml"):
            with self.subTest(accept=accept), self.assertNumQueries(0):
                self.assert_error(self.active_request(HTTP_ACCEPT=accept),
                                  406, "not_acceptable")
        for accept in ("application/json", "*/*"):
            self.assertEqual(self.active_request(HTTP_ACCEPT=accept).status_code, 200)

    def test_discovery_has_no_writes(self):
        Category.objects.create(display_name="Synthetic Topic", is_active=False)
        models = tuple(apps.get_app_config("ledger").get_models())

        def snapshot():
            return {model: list(model.objects.order_by("pk").values()) for model in models}

        before = snapshot()
        with CaptureQueriesContext(connection) as queries:
            response = self.active_request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 1)
        self.assertTrue(queries[0]["sql"].lstrip().upper().startswith("SELECT"))
        self.assertEqual(snapshot(), before)

    def test_adapter_serializes_only_internal_discovery_result(self):
        summary = account_access.CategorySummary(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            display_name="Synthetic Projection", is_active=False,
        )
        with patch("gouda.ledger.api.list_read_categories", return_value=(summary,)) as reader:
            with self.assertNumQueries(0):
                response = self.active_request()
        reader.assert_called_once_with(
            principal_context=account_access.trusted_local_principal_context()
        )
        self.assertEqual(response.json(), {"categories": [{
            "id": str(summary.id), "display_name": summary.display_name, "is_active": False,
        }]})

    def test_service_returns_immutable_materialized_safe_projection(self):
        category = Category.objects.create(display_name="Synthetic Topic")
        with self.assertNumQueries(1):
            summaries = account_access.list_read_categories(
                principal_context=account_access.trusted_local_principal_context()
            )
        self.assertIsInstance(summaries, tuple)
        with self.assertNumQueries(0):
            self.assertEqual(asdict(summaries[0]), {
                "id": category.pk, "display_name": category.display_name, "is_active": True,
            })
        with self.assertRaises(FrozenInstanceError):
            summaries[0].is_active = False

    def test_service_rejects_untrusted_principals_before_database_work(self):
        for principal in (None, object(), "trusted-local-principal",
                          account_access.TrustedPrincipalContext(), Category()):
            with self.subTest(principal_type=type(principal).__name__), self.assertNumQueries(0):
                with self.assertRaises(account_access.AccountAccessServiceError) as caught:
                    account_access.list_read_categories(principal_context=principal)
                self.assertEqual(caught.exception.code, "principal_context_invalid")
