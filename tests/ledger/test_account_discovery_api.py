from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from unittest.mock import patch
from uuid import UUID, uuid4

from django.apps import apps
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from gouda import local_delivery
from gouda.ledger.models import (
    Account,
    ImportBatch,
    Movement,
    RawRecord,
    SantanderTdcAccountBinding,
    SourceArtifact,
)
from gouda.ledger.services import account_access, observation_resolution


class AccountDiscoveryApiTests(TransactionTestCase):
    endpoint = "/api/v1/accounts/"

    def setUp(self):
        self.client = APIClient()

    def make_account(
        self,
        display_name: str,
        *,
        liability: bool = False,
        currency: str = "CLP",
        account_id: UUID | None = None,
    ) -> Account:
        values = {
            "display_name": display_name,
            "kind": Account.Kind.CREDIT_CARD if liability else Account.Kind.CURRENT,
            "economic_orientation": (
                Account.EconomicOrientation.LIABILITY
                if liability
                else Account.EconomicOrientation.ASSET
            ),
            "currency": currency,
        }
        if account_id is not None:
            values["id"] = account_id
        return Account.objects.create(**values)

    def active_get(self, *, params=None, **extra):
        return local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=lambda runtime: self.client.get(
                self.endpoint,
                data=params,
                **extra,
            ),
        )

    def active_request(self, method: str, **extra):
        return local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=lambda runtime: getattr(self.client, method)(
                self.endpoint,
                **extra,
            ),
        )

    def assert_error(self, response, *, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json(), {"code": code})
        self.assertEqual(response["Content-Type"], "application/json")

    def make_private_financial_graph(self, account: Account) -> dict[str, str]:
        content = b"SYNTHETIC_PRIVATE_RAW_SOURCE_DATA"
        artifact = SourceArtifact.objects.create(
            original_filename="SYNTHETIC_PRIVATE_STATEMENT_FILENAME.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            source_variant="SYNTHETIC_PRIVATE_SOURCE_BINDING",
            parser_version="synthetic-private-parser-v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now(timezone.utc),
            reconciliation_status=ImportBatch.ReconciliationStatus.RECONCILED,
        )
        raw = RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=1,
            row_number=1,
            raw_cells=[
                {
                    "column": "A",
                    "value_kind": "string",
                    "value": "SYNTHETIC_EXTERNAL_ACCOUNT_00000001",
                }
            ],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            xlsx_amount_source_column="E",
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            parser_codes=[],
        )
        movement = Movement(
            raw_record=raw,
            account=account,
            occurrence_date=date(2026, 8, 15),
            signed_amount=Decimal("42.00"),
            currency=account.currency,
            description="SYNTHETIC_PRIVATE_MOVEMENT_DESCRIPTION",
            source_reference="SYNTHETIC_PRIVATE_SOURCE_REFERENCE",
            running_balance=Decimal("999999.99"),
        )
        movement.full_clean()
        movement.save()
        observation = observation_resolution.create_financial_observation(
            raw_record_id=raw.pk,
            account_id=account.pk,
            transaction_date=None,
            accounting_date=date(2026, 8, 15),
            signed_amount=Decimal("42.00"),
            currency=account.currency,
            description="SYNTHETIC_PRIVATE_OBSERVATION_DESCRIPTION",
            source_reference="SYNTHETIC_PRIVATE_OBSERVATION_REFERENCE",
            interpretation_method="synthetic_private_interpreter",
            interpretation_version="v1",
            idempotency_key=uuid4(),
        )
        return {
            "artifact_id": str(artifact.pk),
            "batch_id": str(batch.pk),
            "raw_id": str(raw.pk),
            "movement_id": str(movement.pk),
            "observation_id": str(observation.pk),
            "digest": artifact.content_digest,
        }

    def test_success_returns_only_minimal_summaries_with_count_and_stable_order(self):
        same_high = self.make_account("Synthetic Same", liability=True, currency="USD")
        same_low = self.make_account(
            "Synthetic Same",
            account_id=UUID("00000000-0000-4000-8000-000000000001"),
        )
        first = self.make_account("Synthetic Alpha")

        response = self.active_get()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"count", "accounts"})
        self.assertEqual(payload["count"], 3)
        self.assertEqual(
            [item["id"] for item in payload["accounts"]],
            [str(first.pk), str(same_low.pk), str(same_high.pk)],
        )
        self.assertEqual(
            payload["accounts"],
            [
                {
                    "id": str(first.pk),
                    "display_name": "Synthetic Alpha",
                    "kind": Account.Kind.CURRENT,
                    "currency": "CLP",
                },
                {
                    "id": str(same_low.pk),
                    "display_name": "Synthetic Same",
                    "kind": Account.Kind.CURRENT,
                    "currency": "CLP",
                },
                {
                    "id": str(same_high.pk),
                    "display_name": "Synthetic Same",
                    "kind": Account.Kind.CREDIT_CARD,
                    "currency": "USD",
                },
            ],
        )

    def test_empty_database_has_deterministic_empty_response(self):
        first = self.active_get()
        second = self.active_get()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"count": 0, "accounts": []})
        self.assertEqual(second.json(), first.json())

    def test_each_discovered_uuid_selects_existing_movement_report_route(self):
        accounts = (
            self.make_account("Synthetic Current"),
            self.make_account("Synthetic Card", liability=True),
        )

        discovered = self.active_get().json()["accounts"]

        self.assertEqual({item["id"] for item in discovered}, {str(item.pk) for item in accounts})
        for item in discovered:
            with self.subTest(account_id=item["id"]):
                response = local_delivery.run_validated_local_delivery(
                    bind_host="127.0.0.1",
                    port="8000",
                    server_runner=lambda runtime: self.client.get(
                        f"/api/v1/accounts/{item['id']}/movements/",
                        data={"start_date": "2026-08-01", "end_date": "2026-08-31"},
                    ),
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["account_id"], item["id"])

    def test_adapter_can_represent_only_accounts_authorized_by_access_service(self):
        allowed = self.make_account("Synthetic Allowed")
        denied = self.make_account("Synthetic Denied")
        principal = account_access.trusted_local_principal_context()
        with patch.object(
            account_access,
            "_principal_may_read_account",
            side_effect=lambda *, principal_context, account_id: (
                principal_context is principal and account_id != denied.pk
            ),
        ):
            response = self.active_get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["accounts"][0]["id"], str(allowed.pk))
        self.assertNotIn(str(denied.pk), response.content.decode())

    def test_inactive_runtime_fails_before_database_access(self):
        self.make_account("Synthetic Existing")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.endpoint)

        self.assert_error(response, status=503, code="local_delivery_not_active")
        self.assertEqual(queries.captured_queries, [])

    def test_generic_request_cannot_establish_trust(self):
        response = self.client.get(self.endpoint)
        self.assert_error(response, status=503, code="local_delivery_not_active")

    def test_headers_cannot_establish_trust(self):
        response = self.client.get(
            self.endpoint,
            HTTP_X_GOUDA_PRINCIPAL="trusted-local-principal",
            HTTP_AUTHORIZATION="Bearer trusted-local-principal",
            HTTP_HOST="127.0.0.1",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assert_error(response, status=503, code="local_delivery_not_active")

    def test_cookies_cannot_establish_trust(self):
        self.client.cookies["principal"] = "trusted-local-principal"
        response = self.client.get(self.endpoint)
        self.assert_error(response, status=503, code="local_delivery_not_active")

    def test_query_and_body_values_cannot_establish_trust(self):
        response = self.client.generic(
            "GET",
            self.endpoint + "?principal=trusted-local-principal",
            data=b'{"principal":"trusted-local-principal"}',
            content_type="application/json",
        )
        self.assert_error(response, status=503, code="local_delivery_not_active")

    def test_principal_context_rejection_uses_existing_mapping(self):
        self.make_account("Synthetic Existing")
        with patch.object(
            local_delivery.LocalDeliveryRuntime,
            "trusted_principal_context",
            return_value=object(),
        ):
            response = self.active_get()

        self.assert_error(response, status=403, code="principal_context_invalid")

    def test_privacy_sensitive_account_and_financial_graph_data_are_absent(self):
        current = self.make_account("Synthetic Current")
        private_ids = self.make_private_financial_graph(current)
        card = self.make_account("Synthetic Card", liability=True)
        SantanderTdcAccountBinding.objects.create(
            account=card,
            card_last_four="0079",
        )

        response = self.active_get()

        self.assertEqual(response.status_code, 200)
        for summary in response.json()["accounts"]:
            self.assertEqual(
                set(summary),
                {"id", "display_name", "kind", "currency"},
            )
        returned_values = {
            str(value)
            for summary in response.json()["accounts"]
            for value in summary.values()
        }
        self.assertNotIn("0079", returned_values)
        rendered = response.content.decode()
        forbidden = (
            "provider",
            "external_account_id",
            "account_number",
            "card_number",
            "masked",
            "card_last_four",
            "source_binding",
            "source_artifact",
            "import_batch",
            "raw_record",
            "movement",
            "observation",
            "balance",
            "transaction_count",
            "movement_count",
            "SYNTHETIC_PRIVATE_STATEMENT_FILENAME.xlsx",
            "SYNTHETIC_PRIVATE_RAW_SOURCE_DATA",
            "SYNTHETIC_EXTERNAL_ACCOUNT_00000001",
            "SYNTHETIC_PRIVATE_SOURCE_BINDING",
            ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            "synthetic-private-parser-v1",
            ImportBatch.Status.ACCEPTED,
            ImportBatch.ReconciliationStatus.RECONCILED,
            "SYNTHETIC_PRIVATE_MOVEMENT_DESCRIPTION",
            "SYNTHETIC_PRIVATE_SOURCE_REFERENCE",
            "SYNTHETIC_PRIVATE_OBSERVATION_DESCRIPTION",
            "SYNTHETIC_PRIVATE_OBSERVATION_REFERENCE",
            "UNRESOLVED",
            "42.00",
            "999999.99",
            *private_ids.values(),
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, rendered)

    def test_successful_discovery_performs_no_database_writes(self):
        self.make_account("Synthetic Existing")
        model_types = tuple(apps.get_app_config("ledger").get_models())
        before = {model: model.objects.count() for model in model_types}

        with CaptureQueriesContext(connection) as queries:
            response = self.active_get()

        after = {model: model.objects.count() for model in model_types}
        self.assertEqual(response.status_code, 200)
        self.assertEqual(after, before)
        self.assertTrue(queries.captured_queries)
        self.assertTrue(
            all(
                query["sql"].lstrip().upper().startswith("SELECT")
                for query in queries.captured_queries
            )
        )

    def test_get_only_with_intentionally_bounded_head_and_options(self):
        for method in ("post", "put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = self.active_request(method)
                self.assert_error(response, status=405, code="method_not_allowed")

        head = self.active_request("head")
        self.assertEqual(head.status_code, 405)
        self.assertEqual(head.content, b"")

    def test_non_json_representation_is_rejected(self):
        response = self.active_get(HTTP_ACCEPT="text/html")
        self.assert_error(response, status=406, code="not_acceptable")

    def test_every_unexpected_query_parameter_is_rejected_deterministically(self):
        self.make_account("Synthetic Existing")
        for params in (
            {"search": "Synthetic"},
            {"ordering": "display_name"},
            [("unexpected", "one"), ("unexpected", "two")],
        ):
            with self.subTest(params=params):
                response = self.active_get(params=params)
                self.assert_error(
                    response,
                    status=400,
                    code="query_parameters_not_allowed",
                )
