from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from gouda.ledger.models import (
    Account,
    ImportBatch,
    Movement,
    RawRecord,
    SantanderTdcAccountBinding,
    SourceArtifact,
)
from gouda.ledger.validation import validate_exact_money


class LedgerModelTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic checking",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        content = b"synthetic artifact bytes"
        self.artifact = SourceArtifact.objects.create(
            original_filename="synthetic-statement.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )

    def make_batch(self, *, status=ImportBatch.Status.PROCESSING, parser_version="santander-v0.2", **kwargs):
        values = {
            "source_artifact": self.artifact,
            "account": self.account,
            "source_kind": ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            "parser_version": parser_version,
            "status": status,
        }
        if status in {
            ImportBatch.Status.ACCEPTED,
            ImportBatch.Status.PARTIAL,
            ImportBatch.Status.REJECTED,
        }:
            values.update(
                completed_at=datetime.now(timezone.utc),
                reconciliation_status=ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA,
                source_variant="v1",
            )
        if status == ImportBatch.Status.FATAL:
            values.update(
                completed_at=datetime.now(timezone.utc),
                failure_stage=ImportBatch.FailureStage.PARSER,
                failure_code="xlsx_invalid",
            )
        if status == ImportBatch.Status.DUPLICATE:
            values["source_variant"] = "v1"
        values.update(kwargs)
        return ImportBatch.objects.create(**values)

    def make_parsed_raw(self, batch):
        return RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=22,
            row_number=22,
            raw_cells=[{"column": "A", "value_kind": "string", "value": "04/02"}],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            xlsx_amount_source_column="E",
            parser_codes=[],
        )

    def make_isolated_context(self, suffix: str):
        account = Account.objects.create(
            display_name=f"Synthetic account {suffix}",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        content = f"synthetic artifact {suffix}".encode()
        artifact = SourceArtifact.objects.create(
            original_filename=f"synthetic-{suffix}.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        return account, artifact

    def test_uuid_identities_are_generated_and_source_artifact_bytes_are_exact(self):
        self.assertIsInstance(self.account.pk, uuid.UUID)
        self.assertEqual(self.artifact.content, b"synthetic artifact bytes")
        self.assertEqual(self.artifact.original_filename, "synthetic-statement.xlsx")

    def test_account_string_representation_does_not_expose_display_name(self):
        self.assertNotIn("Synthetic checking", str(self.account))
        self.assertIn(str(self.account.pk), str(self.account))

    def test_account_kind_and_orientation_enum_values_are_stable(self):
        self.assertEqual(Account.Kind.CURRENT, "CURRENT")
        self.assertEqual(Account.Kind.CREDIT_CARD, "CREDIT_CARD")
        self.assertEqual(Account.EconomicOrientation.ASSET, "ASSET")
        self.assertEqual(Account.EconomicOrientation.LIABILITY, "LIABILITY")

    def test_supported_kind_orientation_combinations_are_accepted(self):
        current = self.account
        card = Account.objects.create(
            display_name="Synthetic credit card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="ZZZ",
        )
        self.assertEqual(current.economic_orientation, Account.EconomicOrientation.ASSET)
        self.assertEqual(card.economic_orientation, Account.EconomicOrientation.LIABILITY)

    def test_santander_tdc_binding_preserves_suffix_and_is_not_globally_unique(self):
        cards = [
            Account.objects.create(
                display_name=f"Synthetic card {index}",
                kind=Account.Kind.CREDIT_CARD,
                economic_orientation=Account.EconomicOrientation.LIABILITY,
                currency="ZZZ",
            )
            for index in range(2)
        ]
        bindings = []
        for card in cards:
            binding = SantanderTdcAccountBinding(
                account=card,
                card_last_four="0079",
            )
            binding.full_clean()
            binding.save()
            bindings.append(binding)
        self.assertEqual([binding.card_last_four for binding in bindings], ["0079", "0079"])
        self.assertNotIn("0079", str(bindings[0]))

    def test_santander_tdc_binding_rejects_invalid_shape_account_and_duplicate_account(self):
        card = Account.objects.create(
            display_name="Synthetic bound card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="ZZZ",
        )
        for suffix in ("079", "00079", "00A9", "１２３４"):
            with self.subTest(suffix_length=len(suffix)):
                binding = SantanderTdcAccountBinding(account=card, card_last_four=suffix)
                with self.assertRaises(ValidationError):
                    binding.full_clean()

        invalid_account_binding = SantanderTdcAccountBinding(
            account=self.account,
            card_last_four="0079",
        )
        with self.assertRaises(ValidationError):
            invalid_account_binding.full_clean()

        SantanderTdcAccountBinding.objects.create(
            account=card,
            card_last_four="0079",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SantanderTdcAccountBinding.objects.create(
                    account=card,
                    card_last_four="0080",
                )

        other_card = Account.objects.create(
            display_name="Synthetic invalid suffix card",
            kind=Account.Kind.CREDIT_CARD,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="ZZZ",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SantanderTdcAccountBinding.objects.create(
                    account=other_card,
                    card_last_four="079A",
                )

    def test_database_rejects_invalid_kind_orientation_combinations(self):
        invalid = (
            (Account.Kind.CURRENT, Account.EconomicOrientation.LIABILITY),
            (Account.Kind.CREDIT_CARD, Account.EconomicOrientation.ASSET),
        )
        for index, (kind, orientation) in enumerate(invalid):
            with self.subTest(kind=kind, orientation=orientation):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Account.objects.create(
                            display_name=f"Invalid account {index}",
                            kind=kind,
                            economic_orientation=orientation,
                            currency="ZZZ",
                        )

    def test_economic_orientation_is_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    display_name="Missing orientation",
                    kind=Account.Kind.CURRENT,
                    currency="ZZZ",
                )

    def test_orientation_does_not_rewrite_existing_movement_values(self):
        batch = self.make_batch()
        raw_record = self.make_parsed_raw(batch)
        movement = Movement.objects.create(
            raw_record=raw_record,
            account=self.account,
            occurrence_date=date(2026, 4, 2),
            signed_amount=Decimal("-1.25"),
            currency="ZZZ",
        )
        self.account.refresh_from_db()
        movement.refresh_from_db()
        self.assertEqual(self.account.economic_orientation, Account.EconomicOrientation.ASSET)
        self.assertEqual(movement.signed_amount, Decimal("-1.25"))

    def test_exact_money_validator_rejects_rounding_precision_and_nonfinite_values(self):
        validate_exact_money(Decimal("999999999999999999.99"))
        for value in (Decimal("1.001"), Decimal("1000000000000000000.00"), Decimal("NaN"), Decimal("Infinity")):
            with self.assertRaises(ValidationError):
                validate_exact_money(value)

    def test_model_validation_rejects_money_that_database_scale_would_round(self):
        batch = self.make_batch()
        batch.opening_balance = Decimal("1.001")
        with self.assertRaises(ValidationError):
            batch.full_clean()

    def test_source_artifact_digest_is_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SourceArtifact.objects.create(
                    original_filename="another-synthetic-name.xlsx",
                    content_digest=self.artifact.content_digest,
                    content=b"different synthetic bytes",
                )

    def test_import_batch_lifecycle_constraints(self):
        batch = self.make_batch()
        self.assertEqual(batch.status, ImportBatch.Status.PROCESSING)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportBatch.objects.create(
                    source_artifact=self.artifact,
                    account=self.account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                    source_variant="v1",
                    status=ImportBatch.Status.ACCEPTED,
                )

    def test_invalid_materialized_status_counts_are_rejected_by_postgresql(self):
        invalid = [
            {"status": ImportBatch.Status.ACCEPTED, "rejected_count": 1},
            {"status": ImportBatch.Status.PARTIAL, "parsed_count": 0, "rejected_count": 1},
            {"status": ImportBatch.Status.PARTIAL, "parsed_count": 1, "rejected_count": 0},
            {"status": ImportBatch.Status.REJECTED, "parsed_count": 1, "rejected_count": 1},
            {"status": ImportBatch.Status.REJECTED, "parsed_count": 0, "rejected_count": 0},
            {"status": ImportBatch.Status.FATAL, "ignored_count": 1},
        ]
        for index, values in enumerate(invalid):
            with self.subTest(values=values):
                account, artifact = self.make_isolated_context(f"invalid-{index}")
                values.update(
                    source_artifact=artifact,
                    account=account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                )
                if values["status"] in {
                    ImportBatch.Status.ACCEPTED,
                    ImportBatch.Status.PARTIAL,
                    ImportBatch.Status.REJECTED,
                }:
                    values.update(
                        completed_at=datetime.now(timezone.utc),
                        reconciliation_status=ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA,
                        source_variant="v1",
                    )
                elif values["status"] == ImportBatch.Status.FATAL:
                    values.update(
                        completed_at=datetime.now(timezone.utc),
                        failure_stage=ImportBatch.FailureStage.PARSER,
                        failure_code="xlsx_invalid",
                    )
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        ImportBatch.objects.create(**values)

        account, artifact = self.make_isolated_context("invalid-duplicate")
        target = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now(timezone.utc),
            reconciliation_status=ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA,
            source_variant="v1",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportBatch.objects.create(
                    source_artifact=artifact,
                    account=account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                    status=ImportBatch.Status.DUPLICATE,
                    completed_at=datetime.now(timezone.utc),
                    duplicate_of=target,
                    parsed_count=1,
                    source_variant="v1",
                )

        accepted = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        self.assertEqual((accepted.parsed_count, accepted.rejected_count), (0, 0))

    def test_batch_counts_cannot_be_negative_in_postgresql(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_batch(parsed_count=-1)

    def test_one_materialized_batch_per_artifact_and_account_even_if_version_differs(self):
        self.make_batch(status=ImportBatch.Status.ACCEPTED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_batch(status=ImportBatch.Status.PARTIAL, parser_version="future-version")

    def test_one_materialized_batch_per_artifact_and_account_across_source_kinds(self):
        self.make_batch(status=ImportBatch.Status.ACCEPTED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_batch(
                    status=ImportBatch.Status.ACCEPTED,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
                    parser_version="santander-tdc-pdf-v1.1",
                    source_variant="santander_credit_card_pdf",
                )

    def test_fatal_and_duplicate_attempts_can_coexist_with_materialization_rule(self):
        materialized = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        fatal = self.make_batch(status=ImportBatch.Status.FATAL, parser_version="santander-v0.3")
        duplicate = self.make_batch(
            status=ImportBatch.Status.DUPLICATE,
            parser_version="santander-v0.4",
            completed_at=datetime.now(timezone.utc),
            duplicate_of=materialized,
        )
        self.assertEqual(fatal.status, ImportBatch.Status.FATAL)
        self.assertEqual(duplicate.duplicate_of_id, materialized.id)

        second_fatal = self.make_batch(status=ImportBatch.Status.FATAL, parser_version="santander-v0.5")
        second_duplicate = self.make_batch(
            status=ImportBatch.Status.DUPLICATE,
            parser_version="santander-v0.6",
            completed_at=datetime.now(timezone.utc),
            duplicate_of=materialized,
        )
        self.assertEqual(second_fatal.status, ImportBatch.Status.FATAL)
        self.assertEqual(second_duplicate.duplicate_of_id, materialized.id)

    def test_database_rejects_duplicate_self_reference(self):
        batch_id = uuid.uuid4()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportBatch.objects.create(
                    id=batch_id,
                    source_artifact=self.artifact,
                    account=self.account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                    status=ImportBatch.Status.DUPLICATE,
                    duplicate_of_id=batch_id,
                    completed_at=datetime.now(timezone.utc),
                    source_variant="v1",
                )

    def test_duplicate_model_validation_requires_matching_materialized_target(self):
        target = self.make_batch(status=ImportBatch.Status.ACCEPTED)

        processing_target = self.make_batch()
        candidate = self.make_batch(
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=processing_target,
        )
        with self.assertRaises(ValidationError):
            candidate.full_clean()

        other_account = Account.objects.create(
            display_name="Other synthetic account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        mismatched_account = ImportBatch(
            source_artifact=self.artifact,
            account=other_account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=target,
        )
        with self.assertRaises(ValidationError):
            mismatched_account.full_clean()

        other_artifact = SourceArtifact.objects.create(
            original_filename="second-synthetic.xlsx",
            content_digest="1" * 64,
            content=b"second synthetic artifact",
        )
        mismatched_artifact = ImportBatch(
            source_artifact=other_artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=target,
        )
        with self.assertRaises(ValidationError):
            mismatched_artifact.full_clean()

        duplicate_target = self.make_batch(
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=target,
        )
        duplicate_of_duplicate = ImportBatch(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=duplicate_target,
        )
        with self.assertRaises(ValidationError):
            duplicate_of_duplicate.full_clean()

        mismatched_source_kind = ImportBatch(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            parser_version="santander-tdc-pdf-v1.1",
            source_variant="santander_credit_card_pdf",
            status=ImportBatch.Status.DUPLICATE,
            completed_at=datetime.now(timezone.utc),
            duplicate_of=target,
        )
        with self.assertRaises(ValidationError):
            mismatched_source_kind.full_clean()

    def test_source_variant_database_constraints(self):
        processing_without_variant = self.make_batch()
        fatal_without_variant = self.make_batch(status=ImportBatch.Status.FATAL)
        processing_with_variant = self.make_batch(source_variant="v1")
        fatal_with_variant = self.make_batch(status=ImportBatch.Status.FATAL, source_variant="v1")
        self.assertIsNone(processing_without_variant.source_variant)
        self.assertIsNone(fatal_without_variant.source_variant)
        self.assertEqual(processing_with_variant.source_variant, "v1")
        self.assertEqual(fatal_with_variant.source_variant, "v1")

        materialized_statuses = (
            (ImportBatch.Status.ACCEPTED, 0, 0),
            (ImportBatch.Status.PARTIAL, 1, 1),
            (ImportBatch.Status.REJECTED, 0, 1),
        )
        materialized = []
        for index, (status, parsed_count, rejected_count) in enumerate(materialized_statuses):
            account, artifact = self.make_isolated_context(f"variant-valid-{index}")
            batch = ImportBatch.objects.create(
                source_artifact=artifact,
                account=account,
                source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                parser_version="santander-v0.2",
                source_variant="v1",
                status=status,
                completed_at=datetime.now(timezone.utc),
                parsed_count=parsed_count,
                rejected_count=rejected_count,
                reconciliation_status=ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA,
            )
            materialized.append(batch)

        duplicate = ImportBatch.objects.create(
            source_artifact=materialized[0].source_artifact,
            account=materialized[0].account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.DUPLICATE,
            duplicate_of=materialized[0],
            completed_at=datetime.now(timezone.utc),
        )
        self.assertEqual(duplicate.source_variant, "v1")

        required_statuses = (
            (ImportBatch.Status.ACCEPTED, 0, 0),
            (ImportBatch.Status.PARTIAL, 1, 1),
            (ImportBatch.Status.REJECTED, 0, 1),
        )
        for index, (status, parsed_count, rejected_count) in enumerate(required_statuses):
            account, artifact = self.make_isolated_context(f"variant-null-{index}")
            with self.subTest(status=status), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    ImportBatch.objects.create(
                        source_artifact=artifact,
                        account=account,
                        source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                        parser_version="santander-v0.2",
                        source_variant=None,
                        status=status,
                        completed_at=datetime.now(timezone.utc),
                        parsed_count=parsed_count,
                        rejected_count=rejected_count,
                        reconciliation_status=ImportBatch.ReconciliationStatus.INSUFFICIENT_DATA,
                    )

        account, artifact = self.make_isolated_context("variant-null-duplicate")
        target = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="santander-v0.2",
            source_variant="v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now(timezone.utc),
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportBatch.objects.create(
                    source_artifact=artifact,
                    account=account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                    source_variant=None,
                    status=ImportBatch.Status.DUPLICATE,
                    duplicate_of=target,
                    completed_at=datetime.now(timezone.utc),
                )

        account, artifact = self.make_isolated_context("variant-empty")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ImportBatch.objects.create(
                    source_artifact=artifact,
                    account=account,
                    source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                    parser_version="santander-v0.2",
                    source_variant="",
                    status=ImportBatch.Status.PROCESSING,
                )

    def test_raw_record_row_identity_and_outcome_constraints(self):
        batch = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        self.make_parsed_raw(batch)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_parsed_raw(batch)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RawRecord.objects.create(
                    import_batch=batch,
                    record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
                    record_ordinal=23,
                    row_number=23,
                    raw_cells=[],
                    row_class=RawRecord.RowClass.AUXILIARY,
                    parse_outcome="UNKNOWN",
                    parser_codes=[],
                )

    def test_movement_requires_nonzero_amount(self):
        batch = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        raw = self.make_parsed_raw(batch)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Movement.objects.create(
                    raw_record=raw,
                    account=self.account,
                    occurrence_date=date(2026, 2, 4),
                    signed_amount=Decimal("0.00"),
                    currency="ZZZ",
                )

    def test_movement_is_one_to_one_with_raw_record(self):
        batch = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        raw = self.make_parsed_raw(batch)
        values = {
            "raw_record": raw,
            "account": self.account,
            "occurrence_date": date(2026, 2, 4),
            "signed_amount": Decimal("-10.00"),
            "currency": "ZZZ",
        }
        first = Movement.objects.create(**values)
        self.assertIsNotNone(first.pk)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Movement.objects.create(**values)

    def test_movement_clean_preserves_parsed_account_and_currency_invariants(self):
        batch = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        raw = self.make_parsed_raw(batch)
        movement = Movement(
            raw_record=raw,
            account=self.account,
            occurrence_date=date(2026, 2, 4),
            signed_amount=Decimal("-10.00"),
            currency="ZZZ",
        )
        movement.full_clean()

        movement.currency = "USD"
        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_nonparsed_raw_record_cannot_have_movement_through_model_validation(self):
        batch = self.make_batch(status=ImportBatch.Status.ACCEPTED)
        raw = RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=23,
            row_number=23,
            raw_cells=[],
            row_class=RawRecord.RowClass.AUXILIARY,
            parse_outcome=RawRecord.ParseOutcome.IGNORED,
            xlsx_amount_source_column=None,
            parser_codes=["auxiliary_row"],
        )
        movement = Movement(
            raw_record=raw,
            account=self.account,
            occurrence_date=date(2026, 2, 4),
            signed_amount=Decimal("1.00"),
            currency="ZZZ",
        )
        with self.assertRaises(ValidationError):
            movement.full_clean()


class AccountOrientationMigrationTests(TransactionTestCase):
    reset_sequences = True

    def test_existing_current_accounts_are_backfilled_by_0004(self):
        executor = MigrationExecutor(connection)
        migrate_from = [("ledger", "0003_importbatch_source_variant")]
        migrate_to = [("ledger", "0004_account_economic_orientation")]
        executor.migrate(migrate_from)
        try:
            executor = MigrationExecutor(connection)
            old_account = executor.loader.project_state(migrate_from).apps.get_model("ledger", "Account")
            account = old_account.objects.create(
                display_name="Pre-orientation current account",
                kind="CURRENT",
                currency="ZZZ",
            )

            executor = MigrationExecutor(connection)
            executor.migrate(migrate_to)
            executor = MigrationExecutor(connection)
            new_account = executor.loader.project_state(migrate_to).apps.get_model("ledger", "Account")
            account = new_account.objects.get(pk=account.pk)
            self.assertEqual(account.economic_orientation, "ASSET")
        finally:
            executor.migrate([("ledger", "0007_santander_tdc_account_binding")])
