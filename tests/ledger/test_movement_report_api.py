from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from gouda import local_delivery
from gouda.bci_historical_pdf import parse_bci_historical_pdf
from gouda.ledger.models import Account, ImportBatch, Movement, RawRecord, SourceArtifact
from gouda.ledger.services import account_access, santander_import, santander_tdc_import
from gouda.ledger.services.bci_historical_import import (
    import_bci_historical_current_account_pdf,
)
from gouda.ledger.services.bci_historical_policy import (
    resolve_bci_historical_batch,
)
from tests.fixtures.bci_historical import synthetic_bci_historical_pdf
from tests.ledger.test_santander_tdc_evidence import synthetic_result
from tests.test_santander_parser import workbook_bytes


class CanonicalMovementReportApiTests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.account = self.make_account("Primary")
        self.other_account = self.make_account("Other")
        self.next_artifact = 1

    def make_account(self, label: str, *, liability: bool = False) -> Account:
        return Account.objects.create(
            display_name=f"Synthetic {label}",
            kind=(Account.Kind.CREDIT_CARD if liability else Account.Kind.CURRENT),
            economic_orientation=(
                Account.EconomicOrientation.LIABILITY
                if liability
                else Account.EconomicOrientation.ASSET
            ),
            currency="CLP",
        )

    def make_movement(
        self,
        *,
        account: Account | None = None,
        occurrence_date: date = date(2026, 4, 15),
        signed_amount: Decimal = Decimal("1.00"),
        description: str | None = "Synthetic canonical description",
        source_kind: str = ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
        source_variant: str = "synthetic_api_variant",
        parser_version: str = "synthetic-api-v1",
        reconciliation_status: str = ImportBatch.ReconciliationStatus.RECONCILED,
    ) -> Movement:
        account = account or self.account
        ordinal = self.next_artifact
        self.next_artifact += 1
        content = f"SYNTHETIC_PRIVATE_ARTIFACT_{ordinal}".encode()
        artifact = SourceArtifact.objects.create(
            original_filename=f"SYNTHETIC_PRIVATE_FILENAME_{ordinal}.dat",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=source_kind,
            source_variant=source_variant,
            parser_version=parser_version,
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now(timezone.utc),
            reconciliation_status=reconciliation_status,
        )
        record_kind = {
            ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX:
                RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF:
                RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD,
            ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF:
                RawRecord.RecordKind.BCI_HISTORICAL_PDF_RECORD,
        }[source_kind]
        raw_values = {
            "import_batch": batch,
            "record_kind": record_kind,
            "record_ordinal": 1,
            "parse_outcome": RawRecord.ParseOutcome.PARSED,
            "parser_codes": [],
        }
        if record_kind == RawRecord.RecordKind.SANTANDER_XLSX_ROW:
            raw_values.update(
                row_number=1,
                raw_cells=[
                    {
                        "column": "A",
                        "value_kind": "string",
                        "value": "SYNTHETIC_PRIVATE_RAW_CELL",
                    }
                ],
                row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
                xlsx_amount_source_column="E",
            )
        raw_record = RawRecord.objects.create(**raw_values)
        movement = Movement(
            raw_record=raw_record,
            account=account,
            occurrence_date=occurrence_date,
            signed_amount=signed_amount,
            currency=account.currency,
            description=description,
            source_reference="SYNTHETIC_PRIVATE_SOURCE_REFERENCE",
            running_balance=Decimal("999999.99"),
        )
        movement.full_clean()
        movement.save()
        return movement

    def endpoint(self, selector=None) -> str:
        return (
            f"/api/v1/accounts/{selector or self.account.pk}/movements/"
        )

    def api_get(self, *, selector=None, params=None, **extra):
        if params is None:
            params = {"start_date": "2026-04-01", "end_date": "2026-04-30"}

        def request(runtime):
            return self.client.get(
                self.endpoint(selector),
                data=params,
                **extra,
            )

        return local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=request,
        )

    def assert_error(self, response, *, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json(), {"code": code})
        self.assertEqual(response["Content-Type"], "application/json")

    def test_success_serializes_inclusive_exact_ordered_privacy_safe_report(self):
        start = self.make_movement(
            occurrence_date=date(2026, 4, 1),
            signed_amount=Decimal("1234567890123456.78"),
            description="Synthetic approved start",
            source_variant="synthetic_safe_variant",
            parser_version="synthetic-safe-v1",
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        same_day = self.make_movement(
            occurrence_date=date(2026, 4, 30),
            signed_amount=Decimal("-0.01"),
            description="Synthetic approved end",
        )
        self.make_movement(
            occurrence_date=date(2026, 3, 31),
            signed_amount=Decimal("99.00"),
        )
        self.make_movement(
            occurrence_date=date(2026, 5, 1),
            signed_amount=Decimal("99.00"),
        )
        self.make_movement(
            account=self.other_account,
            occurrence_date=date(2026, 4, 15),
            signed_amount=Decimal("99.00"),
        )

        response = self.api_get()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {
                "account_id",
                "start_date",
                "end_date",
                "movement_count",
                "net_signed_amount",
                "movements",
            },
        )
        self.assertEqual(payload["account_id"], str(self.account.pk))
        self.assertEqual(payload["start_date"], "2026-04-01")
        self.assertEqual(payload["end_date"], "2026-04-30")
        self.assertEqual(payload["movement_count"], 2)
        self.assertEqual(payload["net_signed_amount"], "1234567890123456.77")
        self.assertEqual(
            [item["movement_id"] for item in payload["movements"]],
            [str(start.pk), str(same_day.pk)],
        )

        first = payload["movements"][0]
        self.assertEqual(
            set(first),
            {
                "movement_id",
                "account_id",
                "occurrence_date",
                "signed_amount",
                "currency",
                "description",
                "source_trace",
            },
        )
        self.assertEqual(first["account_id"], str(self.account.pk))
        self.assertEqual(first["occurrence_date"], "2026-04-01")
        self.assertEqual(first["signed_amount"], "1234567890123456.78")
        self.assertEqual(first["currency"], "CLP")
        self.assertEqual(first["description"], "Synthetic approved start")
        trace = first["source_trace"]
        self.assertEqual(
            set(trace),
            {
                "raw_record_id",
                "import_batch_id",
                "source_artifact_id",
                "source_kind",
                "source_variant",
                "parser_version",
                "import_status",
                "reconciliation_status",
            },
        )
        self.assertEqual(trace["raw_record_id"], str(start.raw_record_id))
        self.assertEqual(
            trace["import_batch_id"],
            str(start.raw_record.import_batch_id),
        )
        self.assertEqual(
            trace["source_artifact_id"],
            str(start.raw_record.import_batch.source_artifact_id),
        )
        self.assertEqual(trace["source_variant"], "synthetic_safe_variant")
        self.assertEqual(trace["parser_version"], "synthetic-safe-v1")
        self.assertEqual(
            trace["source_kind"],
            ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
        )
        self.assertEqual(trace["import_status"], ImportBatch.Status.ACCEPTED)
        self.assertEqual(
            trace["reconciliation_status"],
            ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )

        rendered = response.content.decode()
        self.assertIn('"signed_amount":"1234567890123456.78"', rendered)
        for forbidden in (
            "SYNTHETIC_PRIVATE_ARTIFACT",
            "SYNTHETIC_PRIVATE_FILENAME",
            "SYNTHETIC_PRIVATE_RAW_CELL",
            "SYNTHETIC_PRIVATE_SOURCE_REFERENCE",
            "999999.99",
            "original_filename",
            "content_digest",
            "raw_cells",
            "source_reference",
            "running_balance",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_route_selects_and_isolates_requested_account(self):
        self.make_movement(signed_amount=Decimal("1.00"))
        selected = self.make_movement(
            account=self.other_account,
            signed_amount=Decimal("2.00"),
        )

        response = self.api_get(selector=self.other_account.pk)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["account_id"], str(self.other_account.pk))
        self.assertEqual(payload["movement_count"], 1)
        self.assertEqual(payload["movements"][0]["movement_id"], str(selected.pk))

    def test_same_date_ordering_is_deterministic_by_movement_uuid(self):
        movements = [
            self.make_movement(
                occurrence_date=date(2026, 4, 10),
                signed_amount=Decimal(value),
            )
            for value in ("3.00", "1.00", "2.00")
        ]
        expected = [str(identifier) for identifier in sorted(item.pk for item in movements)]

        first = self.api_get().json()
        second = self.api_get().json()

        self.assertEqual(
            [item["movement_id"] for item in first["movements"]],
            expected,
        )
        self.assertEqual(first, second)

    def test_nonexistent_and_policy_denied_accounts_are_non_enumerating(self):
        unknown_id = uuid4()
        unknown = self.api_get(selector=unknown_id)
        self.assert_error(
            unknown,
            status=404,
            code="account_not_accessible",
        )

        with patch.object(account_access, "_principal_may_read_account", return_value=False):
            existing_denied = self.api_get(selector=self.account.pk)
            unknown_denied = self.api_get(selector=unknown_id)

        for response in (existing_denied, unknown_denied):
            self.assert_error(
                response,
                status=404,
                code="account_not_accessible",
            )

    def test_malformed_account_uuid_has_stable_selector_error(self):
        response = self.api_get(selector="not-a-canonical-uuid")
        self.assert_error(response, status=400, code="account_selector_invalid")

    def test_missing_duplicate_and_invalid_dates_have_stable_errors(self):
        cases = (
            ({"end_date": "2026-04-30"}, "start_date_invalid"),
            ({"start_date": "2026-04-01"}, "end_date_invalid"),
            (
                [
                    ("start_date", "2026-04-01"),
                    ("start_date", "2026-04-02"),
                    ("end_date", "2026-04-30"),
                ],
                "start_date_invalid",
            ),
            (
                {"start_date": "01/04/2026", "end_date": "2026-04-30"},
                "start_date_invalid",
            ),
            (
                {"start_date": "2026-4-01", "end_date": "2026-04-30"},
                "start_date_invalid",
            ),
            (
                {"start_date": "2026-04-31", "end_date": "2026-04-30"},
                "start_date_invalid",
            ),
            (
                {"start_date": "2026-04-01", "end_date": "30/04/2026"},
                "end_date_invalid",
            ),
            (
                {"start_date": "2026-04-01", "end_date": "2026-02-30"},
                "end_date_invalid",
            ),
        )

        for params, code in cases:
            with self.subTest(code=code, params=params):
                self.assert_error(
                    self.api_get(params=params),
                    status=400,
                    code=code,
                )

    def test_reversed_date_range_has_stable_error(self):
        response = self.api_get(
            params={"start_date": "2026-05-01", "end_date": "2026-04-30"}
        )
        self.assert_error(response, status=400, code="date_range_invalid")

    def test_inactive_runtime_fails_before_selector_parsing_or_database_access(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                self.endpoint("not-a-uuid"),
                data={"start_date": "invalid", "end_date": "invalid"},
            )

        self.assert_error(
            response,
            status=503,
            code="local_delivery_not_active",
        )
        self.assertEqual(queries.captured_queries, [])

    def test_request_values_cannot_establish_principal_trust(self):
        self.client.cookies["principal"] = "trusted-local-principal"
        response = self.client.generic(
            "GET",
            self.endpoint()
            + "?start_date=2026-04-01&end_date=2026-04-30&principal=trusted",
            data=b'{"principal":"trusted-local-principal"}',
            content_type="application/json",
            HTTP_X_GOUDA_PRINCIPAL="trusted-local-principal",
            HTTP_AUTHORIZATION="Bearer trusted-local-principal",
        )

        self.assert_error(
            response,
            status=503,
            code="local_delivery_not_active",
        )

    def test_active_request_values_do_not_influence_principal_issuance(self):
        self.client.cookies["principal"] = "client-value"
        with patch(
            "gouda.ledger.services.account_access.trusted_local_principal_context",
            wraps=account_access.trusted_local_principal_context,
        ) as issuer:
            response = local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="8000",
                server_runner=lambda runtime: self.client.generic(
                    "GET",
                    self.endpoint()
                    + "?start_date=2026-04-01&end_date=2026-04-30"
                    + "&principal=client-value",
                    data=b'{"principal":"client-value"}',
                    content_type="application/json",
                    HTTP_X_GOUDA_PRINCIPAL="client-value",
                    HTTP_AUTHORIZATION="Bearer client-value",
                ),
            )

        self.assertEqual(response.status_code, 200)
        issuer.assert_called_once_with()

    def test_invalid_principal_context_has_stable_forbidden_response(self):
        with patch.object(
            local_delivery.LocalDeliveryRuntime,
            "trusted_principal_context",
            return_value=object(),
        ):
            response = self.api_get()

        self.assert_error(
            response,
            status=403,
            code="principal_context_invalid",
        )

    def test_only_get_is_supported(self):
        for method in ("post", "put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = local_delivery.run_validated_local_delivery(
                    bind_host="127.0.0.1",
                    port="8000",
                    server_runner=lambda runtime: getattr(self.client, method)(
                        self.endpoint(),
                        data={"start_date": "2026-04-01", "end_date": "2026-04-30"},
                    ),
                )
                self.assert_error(
                    response,
                    status=405,
                    code="method_not_allowed",
                )

        head = local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=lambda runtime: self.client.head(self.endpoint()),
        )
        self.assertEqual(head.status_code, 405)
        self.assertEqual(head.content, b"")

    def test_api_is_json_only_and_uses_no_django_authentication(self):
        self.assertIn("rest_framework", settings.INSTALLED_APPS)
        self.assertEqual(settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"], [])
        self.assertEqual(settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"], [])
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
            ["rest_framework.renderers.JSONRenderer"],
        )
        self.assertIsNone(settings.REST_FRAMEWORK["UNAUTHENTICATED_USER"])
        self.assertIsNone(settings.REST_FRAMEWORK["UNAUTHENTICATED_TOKEN"])
        self.assertNotIn("django.contrib.auth", settings.INSTALLED_APPS)

        response = self.api_get(HTTP_ACCEPT="text/html")
        self.assert_error(response, status=406, code="not_acceptable")

    def test_successful_request_is_read_only(self):
        self.make_movement(signed_amount=Decimal("1.00"))
        model_types = tuple(apps.get_app_config("ledger").get_models())
        before = {model: model.objects.count() for model in model_types}

        with CaptureQueriesContext(connection) as queries:
            response = self.api_get()

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

    def test_santander_current_account_import_is_delivered(self):
        content = workbook_bytes(
            period_start="01/04/2026",
            period_end="30/04/2026",
            opening="$10.00",
            ending="$11.00",
            rows=[
                ["01/04", "cargo", "Synthetic debit", "SYN-D", "$1.00", None, "$9.00"],
                ["30/04", "abono", "Synthetic credit", "SYN-C", None, "$2.00", "$11.00"],
            ],
        )
        batch = santander_import.import_santander_current_account_xlsx(
            content=content,
            original_filename="synthetic-current.xlsx",
            account=self.account,
        )

        payload = self.api_get().json()

        self.assertEqual(payload["movement_count"], 2)
        self.assertEqual(payload["net_signed_amount"], "1.00")
        self.assertTrue(
            all(
                item["source_trace"]["import_batch_id"] == str(batch.pk)
                and item["source_trace"]["source_kind"]
                == ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX
                for item in payload["movements"]
            )
        )

    def test_santander_tdc_import_is_delivered_with_canonical_sign(self):
        account = self.make_account("Card", liability=True)
        santander_tdc_import.configure_santander_tdc_account_binding(
            account=account,
            card_last_four="0079",
        )
        with patch.object(
            santander_tdc_import,
            "parse_tdc_pdf",
            return_value=synthetic_result(),
        ):
            batch = santander_tdc_import.import_santander_credit_card_pdf(
                content=b"privacy-safe synthetic TDC artifact",
                original_filename="synthetic-card.pdf",
                account=account,
            )

        response = self.api_get(
            selector=account.pk,
            params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["movement_count"], 1)
        self.assertEqual(payload["net_signed_amount"], "-22303.00")
        self.assertEqual(payload["movements"][0]["signed_amount"], "-22303.00")
        self.assertEqual(
            payload["movements"][0]["source_trace"]["import_batch_id"],
            str(batch.pk),
        )

    def test_resolved_bci_historical_import_is_delivered(self):
        content = synthetic_bci_historical_pdf(
            rows=({"date": date(2026, 4, 15), "credit": 1200},),
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
        )
        parsed = parse_bci_historical_pdf(content)
        batch = import_bci_historical_current_account_pdf(
            content=content,
            original_filename="synthetic-historical.pdf",
            account=self.account,
            expected_source_account_id=parsed.metadata.source_account_id,
        )
        resolve_bci_historical_batch(import_batch_id=batch.pk)

        response = self.api_get()
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["movement_count"], 1)
        self.assertEqual(payload["net_signed_amount"], "1200.00")
        self.assertEqual(
            payload["movements"][0]["source_trace"]["source_kind"],
            ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF,
        )
