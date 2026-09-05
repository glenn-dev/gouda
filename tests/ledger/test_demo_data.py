from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from gouda import local_delivery
from gouda.ledger.demo_data import (
    DEMO_ACCOUNT_IDS,
    DEMO_ARTIFACT_IDS,
    DEMO_BATCH_IDS,
    DEMO_MOVEMENT_IDS,
    DEMO_RAW_RECORD_IDS,
    DemoDataError,
    MOVEMENT_SPECS,
    clear_demo_data,
    demo_uuid,
    seed_demo_data,
)
from gouda.ledger.models import (
    Account,
    FinancialObservation,
    ImportBatch,
    Movement,
    ObservationResolution,
    RawRecord,
    SourceArtifact,
)


class DemoDataTests(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_empty_database_seed_creates_expected_schema_valid_accounts(self):
        result = seed_demo_data()

        self.assertEqual(result.accounts, 2)
        self.assertEqual(result.movements, 11)
        accounts = list(Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).order_by("display_name"))
        self.assertEqual(
            [
                (item.display_name, item.kind, item.economic_orientation, item.currency)
                for item in accounts
            ],
            [
                (
                    "Synthetic Everyday Account",
                    Account.Kind.CURRENT,
                    Account.EconomicOrientation.ASSET,
                    "CLP",
                ),
                (
                    "Synthetic Household Card",
                    Account.Kind.CREDIT_CARD,
                    Account.EconomicOrientation.LIABILITY,
                    "CLP",
                ),
            ],
        )
        for account in accounts:
            account.full_clean()
        self.assertEqual(
            set(
                ImportBatch.objects.filter(pk__in=DEMO_BATCH_IDS).values_list(
                    "source_kind", flat=True
                )
            ),
            {ImportBatch.SourceKind.DEMO_SYNTHETIC},
        )
        self.assertEqual(
            set(
                RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).values_list(
                    "record_kind", flat=True
                )
            ),
            {RawRecord.RecordKind.DEMO_SYNTHETIC_RECORD},
        )

    def test_seed_creates_exact_deterministic_canonical_movement_values(self):
        seed_demo_data()

        actual = {
            str(item.pk): (
                item.occurrence_date,
                item.signed_amount,
                item.currency,
                item.description,
                item.source_reference,
                item.running_balance,
            )
            for item in Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS)
        }
        expected = {
            str(_movement_id(spec.key)): (
                spec.occurrence_date,
                spec.signed_amount,
                "CLP",
                spec.description,
                None,
                None,
            )
            for spec in MOVEMENT_SPECS
        }
        self.assertEqual(actual, expected)
        self.assertTrue(all(isinstance(item[1], Decimal) for item in actual.values()))
        for movement in Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS):
            movement.full_clean()

    def test_asset_and_liability_signs_follow_canonical_account_effect(self):
        seed_demo_data()

        current = Account.objects.get(display_name="Synthetic Everyday Account")
        card = Account.objects.get(display_name="Synthetic Household Card")
        current_values = {
            item.description: item.signed_amount for item in current.movements.all()
        }
        card_values = {
            item.description: item.signed_amount for item in card.movements.all()
        }

        self.assertGreater(current_values["Synthetic salary deposit"], 0)
        self.assertLess(current_values["Synthetic grocery purchase"], 0)
        self.assertLess(card_values["Synthetic card grocery purchase"], 0)
        self.assertGreater(card_values["Synthetic liability balance reduction"], 0)
        self.assertGreater(card_values["Synthetic card refund"], 0)

    def test_seed_is_idempotent_without_duplicates(self):
        first = seed_demo_data()
        first_graph = self._demo_graph_snapshot()
        second = seed_demo_data()

        self.assertEqual(second, first)
        self.assertEqual(self._demo_graph_snapshot(), first_graph)
        self.assertEqual(Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).count(), 2)
        self.assertEqual(SourceArtifact.objects.filter(pk__in=DEMO_ARTIFACT_IDS).count(), 2)
        self.assertEqual(ImportBatch.objects.filter(pk__in=DEMO_BATCH_IDS).count(), 2)
        self.assertEqual(RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).count(), 11)
        self.assertEqual(Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS).count(), 11)

    def test_clear_then_reseed_recreates_the_same_graph(self):
        seed_demo_data()
        before = self._demo_graph_snapshot()
        clear_demo_data()
        seed_demo_data()

        self.assertEqual(self._demo_graph_snapshot(), before)

    def test_account_discovery_and_reports_return_seeded_canonical_data(self):
        seed_demo_data()

        discovered = self._active_get("/api/v1/accounts/")
        self.assertEqual(discovered.status_code, 200)
        self.assertEqual(discovered.json()["count"], 2)
        by_name = {
            item["display_name"]: item for item in discovered.json()["accounts"]
        }

        current_id = by_name["Synthetic Everyday Account"]["id"]
        april = self._active_get(
            f"/api/v1/accounts/{current_id}/movements/",
            {"start_date": "2026-04-01", "end_date": "2026-04-30"},
        )
        self.assertEqual(april.status_code, 200)
        self.assertEqual(april.json()["movement_count"], 3)
        self.assertEqual(april.json()["net_signed_amount"], "2476240.00")

        march = self._active_get(
            f"/api/v1/accounts/{current_id}/movements/",
            {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        )
        self.assertEqual(march.json()["movement_count"], 0)
        self.assertEqual(march.json()["net_signed_amount"], "0.00")

        card_id = by_name["Synthetic Household Card"]["id"]
        card_report = self._active_get(
            f"/api/v1/accounts/{card_id}/movements/",
            {"start_date": "2026-01-01", "end_date": "2026-04-30"},
        )
        self.assertEqual(card_report.status_code, 200)
        self.assertEqual(card_report.json()["movement_count"], 5)
        self.assertEqual(card_report.json()["net_signed_amount"], "-38310.00")

    def test_seed_adds_no_classification_transfer_or_observation_semantics(self):
        seed_demo_data()

        movement_fields = {field.name for field in Movement._meta.get_fields()}
        self.assertTrue(
            {"classification", "category", "transfer"}.isdisjoint(movement_fields)
        )
        self.assertFalse(
            FinancialObservation.objects.filter(raw_record_id__in=DEMO_RAW_RECORD_IDS).exists()
        )
        self.assertFalse(ObservationResolution.objects.exists())
        self.assertTrue(
            all(
                value is None
                for value in Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS)
                .values_list("source_reference", flat=True)
            )
        )

    def test_clear_is_idempotent_and_removes_the_complete_demo_graph(self):
        seed_demo_data()

        first = clear_demo_data()
        second = clear_demo_data()

        self.assertEqual(first.accounts, 2)
        self.assertEqual(first.movements, 11)
        self.assertEqual(second.accounts, 0)
        self.assertEqual(second.movements, 0)
        self.assertFalse(Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).exists())
        self.assertFalse(SourceArtifact.objects.filter(pk__in=DEMO_ARTIFACT_IDS).exists())
        self.assertFalse(ImportBatch.objects.filter(pk__in=DEMO_BATCH_IDS).exists())
        self.assertFalse(RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).exists())
        self.assertFalse(Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS).exists())

    def test_clear_preserves_unrelated_synthetic_and_import_like_rows(self):
        seed_demo_data()
        unrelated = self._make_unrelated_graph()
        same_name = Account.objects.create(
            display_name="Synthetic Everyday Account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )

        clear_demo_data()

        for model, object_id in unrelated:
            self.assertTrue(model.objects.filter(pk=object_id).exists())
        self.assertTrue(Account.objects.filter(pk=same_name.pk).exists())

    def test_clear_fails_closed_and_rolls_back_when_foreign_evidence_is_attached(self):
        seed_demo_data()
        before = self._demo_graph_snapshot()
        raw = RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).first()
        assert raw is not None
        observation = FinancialObservation.objects.create(
            raw_record=raw,
            account=raw.import_batch.account,
            transaction_date=date(2026, 1, 5),
            accounting_date=None,
            signed_amount=Decimal("1.00"),
            currency="CLP",
            description="Synthetic foreign protected observation",
            source_reference=None,
            interpretation_method="synthetic_foreign_test",
            interpretation_version="v1",
            idempotency_key=uuid4(),
        )

        with self.assertRaisesRegex(
            DemoDataError,
            "demo_cleanup_blocked_by_non_demo_data",
        ):
            clear_demo_data()

        self.assertEqual(self._demo_graph_snapshot(), before)
        self.assertTrue(FinancialObservation.objects.filter(pk=observation.pk).exists())
        observation.delete()
        clear_demo_data()

    def test_commands_are_repeatable_and_report_bounded_counts(self):
        output = StringIO()
        call_command("seed_demo", stdout=output)
        call_command("seed_demo", stdout=output)
        self.assertEqual(output.getvalue().count("2 Accounts, 11 Movements"), 2)

        output = StringIO()
        call_command("clear_demo", stdout=output)
        call_command("clear_demo", stdout=output)
        self.assertIn("2 Accounts, 11 Movements", output.getvalue())
        self.assertIn("0 Accounts, 0 Movements", output.getvalue())

    def test_seed_and_clear_do_not_access_the_filesystem(self):
        filesystem_access = AssertionError("demo commands must not access files")
        with patch("builtins.open", side_effect=filesystem_access):
            with patch("pathlib.Path.open", side_effect=filesystem_access):
                seed_demo_data()
                clear_demo_data()

    def _active_get(self, path: str, data=None):
        return local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=lambda runtime: self.client.get(path, data=data),
        )

    def _demo_graph_snapshot(self):
        return {
            "accounts": set(Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).values_list("id", flat=True)),
            "artifacts": set(SourceArtifact.objects.filter(pk__in=DEMO_ARTIFACT_IDS).values_list("id", flat=True)),
            "batches": set(ImportBatch.objects.filter(pk__in=DEMO_BATCH_IDS).values_list("id", flat=True)),
            "records": set(RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).values_list("id", flat=True)),
            "movements": {
                (item.pk, item.account_id, item.occurrence_date, item.signed_amount, item.description)
                for item in Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS)
            },
        }

    def _make_unrelated_graph(self):
        account = Account.objects.create(
            display_name="Synthetic unrelated test account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )
        content = b"SYNTHETIC UNRELATED IMPORT-LIKE CONTENT"
        artifact = SourceArtifact.objects.create(
            original_filename="synthetic-unrelated.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="synthetic-unrelated-v1",
            source_variant="synthetic_unrelated",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            parsed_count=1,
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        raw = RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=1,
            row_number=1,
            raw_cells=[{"column": "A", "value_kind": "string", "value": "SYNTHETIC"}],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            xlsx_amount_source_column="F",
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            parser_codes=[],
        )
        movement = Movement.objects.create(
            raw_record=raw,
            account=account,
            occurrence_date=date(2026, 6, 1),
            signed_amount=Decimal("1.00"),
            currency="CLP",
            description="Synthetic unrelated movement",
        )
        observation = FinancialObservation.objects.create(
            raw_record=raw,
            account=account,
            transaction_date=date(2026, 6, 1),
            accounting_date=None,
            signed_amount=Decimal("1.00"),
            currency="CLP",
            description="Synthetic unrelated observation",
            source_reference=None,
            interpretation_method="synthetic_unrelated_test",
            interpretation_version="v1",
            idempotency_key=uuid4(),
        )
        return (
            (Account, account.pk),
            (SourceArtifact, artifact.pk),
            (ImportBatch, batch.pk),
            (RawRecord, raw.pk),
            (Movement, movement.pk),
            (FinancialObservation, observation.pk),
        )


def _movement_id(key: str):
    return demo_uuid("movement", key)
