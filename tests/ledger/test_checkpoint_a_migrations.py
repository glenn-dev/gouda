from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


MIGRATE_FROM = [("ledger", "0004_account_economic_orientation")]
MIGRATE_TO = [("ledger", "0008_observation_resolution_boundary")]
MIGRATE_BINDING_FROM = [("ledger", "0006_checkpoint_a_persistence_boundary")]
MIGRATE_OBSERVATION_FROM = [("ledger", "0007_santander_tdc_account_binding")]
XLSX_SOURCE_KIND = "SANTANDER_CURRENT_ACCOUNT_XLSX"


class CheckpointAMigrationTests(TransactionTestCase):
    reset_sequences = True

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def test_historical_xlsx_graph_backfills_without_canonical_or_artifact_changes(self):
        old_apps = self.migrate(MIGRATE_FROM)
        try:
            Account = old_apps.get_model("ledger", "Account")
            SourceArtifact = old_apps.get_model("ledger", "SourceArtifact")
            ImportBatch = old_apps.get_model("ledger", "ImportBatch")
            RawRecord = old_apps.get_model("ledger", "RawRecord")
            Movement = old_apps.get_model("ledger", "Movement")

            account = Account.objects.create(
                display_name="Historical synthetic current",
                kind="CURRENT",
                economic_orientation="ASSET",
                currency="CLP",
            )
            content = b"historical synthetic workbook"
            digest = hashlib.sha256(content).hexdigest()
            artifact = SourceArtifact.objects.create(
                source_kind=XLSX_SOURCE_KIND,
                original_filename="historical-synthetic.xlsx",
                content_digest=digest,
                content=content,
            )
            batch = ImportBatch.objects.create(
                source_artifact=artifact,
                account=account,
                parser_version="santander-v0.2",
                source_variant="v1",
                status="ACCEPTED",
                completed_at=datetime.now(timezone.utc),
                parsed_count=1,
                ignored_count=1,
                reconciliation_status="RECONCILED",
                opening_balance=Decimal("100.00"),
                ending_balance=Decimal("90.00"),
                reconciliation_difference=Decimal("0.00"),
            )
            parsed_raw = RawRecord.objects.create(
                import_batch=batch,
                row_number=7,
                raw_cells={"schema": "santander-source-row-v1", "cells": []},
                row_class="movement_candidate",
                parse_outcome="PARSED",
                parser_codes=[],
            )
            ignored_raw = RawRecord.objects.create(
                import_batch=batch,
                row_number=8,
                raw_cells={"schema": "santander-source-row-v1", "cells": []},
                row_class="auxiliary",
                parse_outcome="IGNORED",
                parser_codes=["auxiliary_row"],
            )
            movement = Movement.objects.create(
                raw_record=parsed_raw,
                account=account,
                occurrence_date=date(2026, 6, 15),
                signed_amount=Decimal("-10.00"),
                currency="CLP",
                description="Synthetic movement",
                source_reference="SYN-001",
                running_balance=Decimal("90.00"),
                amount_source_column="E",
            )
            ids = {
                "artifact": artifact.pk,
                "batch": batch.pk,
                "parsed_raw": parsed_raw.pk,
                "ignored_raw": ignored_raw.pk,
                "movement": movement.pk,
            }

            new_apps = self.migrate(MIGRATE_TO)
            NewSourceArtifact = new_apps.get_model("ledger", "SourceArtifact")
            NewImportBatch = new_apps.get_model("ledger", "ImportBatch")
            NewRawRecord = new_apps.get_model("ledger", "RawRecord")
            NewMovement = new_apps.get_model("ledger", "Movement")

            migrated_artifact = NewSourceArtifact.objects.get(pk=ids["artifact"])
            migrated_batch = NewImportBatch.objects.get(pk=ids["batch"])
            migrated_parsed = NewRawRecord.objects.get(pk=ids["parsed_raw"])
            migrated_ignored = NewRawRecord.objects.get(pk=ids["ignored_raw"])
            migrated_movement = NewMovement.objects.get(pk=ids["movement"])

            self.assertEqual(bytes(migrated_artifact.content), content)
            self.assertEqual(migrated_artifact.content_digest, digest)
            self.assertEqual(migrated_batch.source_kind, XLSX_SOURCE_KIND)
            self.assertEqual(
                (migrated_parsed.record_kind, migrated_parsed.record_ordinal),
                ("SANTANDER_XLSX_ROW", 7),
            )
            self.assertEqual(migrated_parsed.xlsx_amount_source_column, "E")
            self.assertEqual(
                (migrated_ignored.record_kind, migrated_ignored.record_ordinal),
                ("SANTANDER_XLSX_ROW", 8),
            )
            self.assertIsNone(migrated_ignored.xlsx_amount_source_column)
            self.assertEqual(migrated_movement.signed_amount, Decimal("-10.00"))
            self.assertEqual(migrated_movement.running_balance, Decimal("90.00"))
            self.assertEqual(migrated_movement.source_reference, "SYN-001")
            self.assertNotIn("amount_source_column", {field.name for field in NewMovement._meta.fields})
            self.assertNotIn("source_kind", {field.name for field in NewSourceArtifact._meta.fields})
        finally:
            self.migrate(MIGRATE_TO)

    def test_unknown_historical_source_kind_fails_forward(self):
        old_apps = self.migrate(MIGRATE_FROM)
        try:
            SourceArtifact = old_apps.get_model("ledger", "SourceArtifact")
            content = b"unknown synthetic source"
            artifact = SourceArtifact.objects.create(
                source_kind="UNEXPECTED_SOURCE",
                original_filename="unknown.synthetic",
                content_digest=hashlib.sha256(content).hexdigest(),
                content=content,
            )
            with self.assertRaisesRegex(RuntimeError, "unknown SourceArtifact source kinds"):
                self.migrate(MIGRATE_TO)
            SourceArtifact.objects.filter(pk=artifact.pk).delete()
        finally:
            self.migrate(MIGRATE_TO)

    def test_reverse_refuses_non_xlsx_interpretation(self):
        self.migrate(MIGRATE_TO)
        from gouda.ledger.models import Account, ImportBatch, SourceArtifact

        account = Account.objects.create(
            display_name="Synthetic card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="CLP",
        )
        content = b"synthetic reverse guard"
        artifact = SourceArtifact.objects.create(
            original_filename="synthetic.pdf",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            parser_version="santander-tdc-pdf-v1.1",
            status=ImportBatch.Status.PROCESSING,
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "non-XLSX batches"):
                self.migrate(MIGRATE_FROM)
        finally:
            # The failed reverse leaves the schema before the uncommitted BCI
            # migration. Raw-delete these isolated synthetic rows so Django's
            # live-model collector does not query absent BCI relations.
            ImportBatch.objects.filter(pk=batch.pk)._raw_delete(using="default")
            SourceArtifact.objects.filter(pk=artifact.pk)._raw_delete(using="default")
            Account.objects.filter(pk=account.pk)._raw_delete(using="default")
            self.migrate(MIGRATE_TO)

    def test_binding_migration_adds_only_empty_binding_table(self):
        old_apps = self.migrate(MIGRATE_BINDING_FROM)
        try:
            Account = old_apps.get_model("ledger", "Account")
            SourceArtifact = old_apps.get_model("ledger", "SourceArtifact")
            ImportBatch = old_apps.get_model("ledger", "ImportBatch")
            account = Account.objects.create(
                display_name="Pre-binding synthetic card",
                kind="CREDIT_CARD",
                economic_orientation="LIABILITY",
                currency="CLP",
            )
            content = b"pre-binding synthetic artifact"
            artifact = SourceArtifact.objects.create(
                original_filename="synthetic.pdf",
                content_digest=hashlib.sha256(content).hexdigest(),
                content=content,
            )
            batch = ImportBatch.objects.create(
                source_artifact=artifact,
                account=account,
                source_kind="SANTANDER_CREDIT_CARD_PDF",
                parser_version="santander-tdc-pdf-v1.1",
                status="PROCESSING",
            )

            new_apps = self.migrate(MIGRATE_TO)
            NewAccount = new_apps.get_model("ledger", "Account")
            NewSourceArtifact = new_apps.get_model("ledger", "SourceArtifact")
            NewImportBatch = new_apps.get_model("ledger", "ImportBatch")
            Binding = new_apps.get_model("ledger", "SantanderTdcAccountBinding")
            self.assertTrue(NewAccount.objects.filter(pk=account.pk).exists())
            self.assertTrue(NewSourceArtifact.objects.filter(pk=artifact.pk).exists())
            self.assertTrue(NewImportBatch.objects.filter(pk=batch.pk).exists())
            self.assertFalse(Binding.objects.exists())
        finally:
            self.migrate(MIGRATE_TO)

    def test_binding_migration_reverse_fails_closed_with_configured_binding(self):
        apps = self.migrate(MIGRATE_TO)
        Account = apps.get_model("ledger", "Account")
        Binding = apps.get_model("ledger", "SantanderTdcAccountBinding")
        account = Account.objects.create(
            display_name="Synthetic reverse-bound card",
            kind="CREDIT_CARD",
            economic_orientation="LIABILITY",
            currency="CLP",
        )
        binding = Binding.objects.create(account=account, card_last_four="0079")
        try:
            with self.assertRaisesRegex(RuntimeError, "while bindings exist"):
                self.migrate(MIGRATE_BINDING_FROM)
        finally:
            Binding.objects.filter(pk=binding.pk).delete()
            self.migrate(MIGRATE_TO)
            Account.objects.filter(pk=account.pk).delete()

    def test_observation_boundary_adds_empty_tables_without_rewriting_santander(self):
        old_apps = self.migrate(MIGRATE_OBSERVATION_FROM)
        try:
            Account = old_apps.get_model("ledger", "Account")
            SourceArtifact = old_apps.get_model("ledger", "SourceArtifact")
            ImportBatch = old_apps.get_model("ledger", "ImportBatch")
            RawRecord = old_apps.get_model("ledger", "RawRecord")
            Movement = old_apps.get_model("ledger", "Movement")
            account = Account.objects.create(
                display_name="Pre-observation synthetic account",
                kind="CURRENT",
                economic_orientation="ASSET",
                currency="CLP",
            )
            content = b"pre-observation synthetic artifact"
            artifact = SourceArtifact.objects.create(
                original_filename="pre-observation.xlsx",
                content_digest=hashlib.sha256(content).hexdigest(),
                content=content,
            )
            batch = ImportBatch.objects.create(
                source_artifact=artifact,
                account=account,
                source_kind=XLSX_SOURCE_KIND,
                parser_version="santander-v0.2",
                source_variant="v1",
                status="ACCEPTED",
                completed_at=datetime.now(timezone.utc),
                parsed_count=1,
                reconciliation_status="RECONCILED",
                opening_balance=Decimal("100.00"),
                ending_balance=Decimal("90.00"),
                reconciliation_difference=Decimal("0.00"),
            )
            raw = RawRecord.objects.create(
                import_batch=batch,
                record_kind="SANTANDER_XLSX_ROW",
                record_ordinal=7,
                row_number=7,
                raw_cells={"schema": "santander-source-row-v1", "cells": []},
                row_class="movement_candidate",
                xlsx_amount_source_column="E",
                parse_outcome="PARSED",
                parser_codes=[],
            )
            movement = Movement.objects.create(
                raw_record=raw,
                account=account,
                occurrence_date=date(2026, 6, 15),
                signed_amount=Decimal("-10.00"),
                currency="CLP",
                description="Synthetic movement",
                source_reference="SYN-OBS-MIGRATION",
                running_balance=Decimal("90.00"),
            )

            new_apps = self.migrate(MIGRATE_TO)
            NewMovement = new_apps.get_model("ledger", "Movement")
            Observation = new_apps.get_model("ledger", "FinancialObservation")
            Resolution = new_apps.get_model("ledger", "ObservationResolution")
            migrated = NewMovement.objects.get(pk=movement.pk)

            self.assertEqual(migrated.raw_record_id, raw.pk)
            self.assertEqual(migrated.signed_amount, Decimal("-10.00"))
            self.assertEqual(migrated.currency, "CLP")
            self.assertEqual(migrated.occurrence_date, date(2026, 6, 15))
            self.assertEqual(migrated.running_balance, Decimal("90.00"))
            self.assertEqual(migrated.source_reference, "SYN-OBS-MIGRATION")
            self.assertFalse(Observation.objects.exists())
            self.assertFalse(Resolution.objects.exists())
        finally:
            self.migrate(MIGRATE_TO)
