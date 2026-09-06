from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from gouda.ledger.models import (
    Account, Category, Movement, MovementClassification, RawRecord, ImportBatch,
    SourceArtifact, FinancialObservation, ObservationResolution,
)
from gouda.ledger.services import movement_classification as service
from gouda.ledger.services.movement_reporting import report_canonical_movements
from gouda.ledger.services import account_access
from gouda import local_delivery
from tests.fixtures.movement_classification import make_movement


class CategoryTests(TestCase):
    def test_exact_fields_uuid_default_active_and_preserved_casing(self):
        category = Category.objects.create(display_name="  GroCERies  ")
        category.refresh_from_db()
        self.assertIsInstance(category.pk, UUID)
        self.assertEqual(category.display_name, "GroCERies")
        self.assertTrue(category.is_active)
        self.assertEqual({f.name for f in Category._meta.fields},
                         {"id", "display_name", "is_active"})
        self.assertNotIn(category.display_name, str(category))
        category.is_active = False
        category.save(update_fields=["is_active"])
        category.refresh_from_db()
        self.assertFalse(category.is_active)

    def test_required_normalized_label_shape(self):
        for value in (None, "", " \t\n\u00a0", "A\x00B", "A\nB", "x" * 81):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Category.objects.create(display_name=value)
        category = Category.objects.create(display_name=" Cafe\u0301 ")
        self.assertEqual(category.display_name, "Café")

    def test_database_rejects_exact_and_case_insensitive_duplicates_including_inactive(self):
        Category.objects.create(display_name="Groceries", is_active=False)
        for name in ("Groceries", "gROCERIES"):
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                # bulk_create bypasses save, clean and all service validation.
                Category.objects.bulk_create([Category(display_name=name)])
        self.assertEqual(Category.objects.count(), 1)

    def test_database_rejects_empty_label_and_duplicate_rename(self):
        first = Category.objects.create(display_name="Groceries")
        second = Category.objects.create(display_name="Utilities")
        for name in ("", "GROCERIES"):
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                Category.objects.filter(pk=second.pk).update(display_name=name)
        first.refresh_from_db()
        self.assertEqual(first.display_name, "Groceries")

    def test_raw_sql_cannot_bypass_uniqueness_or_nonempty_constraints(self):
        Category.objects.create(display_name="Groceries", is_active=False)
        for name in ("Groceries", "GROCERIES", "", None):
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO ledger_category (id, display_name, is_active) VALUES (%s, %s, %s)",
                        [uuid4(), name, True],
                    )
        self.assertEqual(Category.objects.count(), 1)

    def test_bulk_update_and_sql_bypass_only_application_label_normalization(self):
        # These are deliberately unsupported provisioning paths. The database
        # guarantees nonempty text, not the model's Unicode/trim/control rules.
        original = "  Cafe\u0301  "
        category = Category.objects.bulk_create([Category(display_name=original)])[0]
        category.refresh_from_db()
        self.assertEqual(category.display_name, original)
        Category.objects.filter(pk=category.pk).update(display_name=" \t ")
        category.refresh_from_db()
        self.assertEqual(category.display_name, " \t ")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ledger_category SET display_name = %s WHERE id = %s",
                           ["Synthetic\nLabel", category.pk])
        category.refresh_from_db()
        self.assertEqual(category.display_name, "Synthetic\nLabel")
        with self.assertRaises(ValidationError):
            category.save()


class MovementClassificationTests(TestCase):
    def setUp(self):
        self.movement = make_movement()
        self.account = self.movement.account
        self.category = Category.objects.create(display_name="Groceries")
        self.other = Category.objects.create(display_name="Utilities")

    def command(self, category, revision, **overrides):
        values = dict(account=self.account, movement_id=self.movement.pk,
                      category_id=category.pk if category else None, expected_revision=revision)
        values.update(overrides)
        return service.set_movement_classification(**values)

    def assert_error(self, code, **values):
        with self.assertRaises(service.MovementClassificationServiceError) as caught:
            self.command(self.category, 0, **values)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def snapshot(self):
        return {model: list(model.objects.order_by("pk").values()) for model in (
            Account, Movement, RawRecord, ImportBatch, SourceArtifact,
            FinancialObservation, ObservationResolution,
        )}

    def test_assign_change_clear_reassign_preserves_financial_and_provenance_values(self):
        before = self.snapshot()
        self.assertFalse(MovementClassification.objects.exists())
        previous_time = None
        clock = timezone.now()
        for revision, category in enumerate((self.category, self.other, None, self.category), 1):
            with patch.object(service.timezone, "now", return_value=clock + timedelta(seconds=revision)):
                result = self.command(category, revision - 1)
            row = MovementClassification.objects.get()
            self.assertEqual(row.pk, self.movement.pk)
            self.assertEqual(row.category_id, category.pk if category else None)
            self.assertEqual(result.category_id, row.category_id)
            self.assertEqual(row.revision, revision)
            self.assertEqual(row.source, "MANUAL")
            self.assertTrue(timezone.is_aware(row.updated_at))
            self.assertNotEqual(row.updated_at, previous_time)
            previous_time = row.updated_at
            self.assertEqual(self.snapshot(), before)
        with self.assertRaises(FrozenInstanceError):
            result.revision = 99

    def test_exact_relation_fields_and_protected_references(self):
        self.command(self.category, 0)
        self.assertEqual({f.name for f in MovementClassification._meta.fields},
                         {"movement", "category", "source", "revision", "updated_at"})
        self.assertEqual(MovementClassification._meta.pk.name, "movement")
        self.assertEqual(MovementClassification.Source.values, ["MANUAL"])
        for obj in (self.movement, self.category):
            with self.assertRaises(ProtectedError):
                obj.delete()

    def test_noops_preserve_timestamp_revision_and_absence(self):
        empty = self.command(None, 0)
        self.assertEqual((empty.category_id, empty.source, empty.revision, empty.updated_at),
                         (None, None, 0, None))
        self.assertFalse(MovementClassification.objects.exists())
        assigned = self.command(self.category, 0)
        self.assertEqual(self.command(self.category, 1), assigned)
        cleared = self.command(None, 1)
        self.assertEqual(self.command(None, 2), cleared)

    def test_stale_revision_fails_before_noop_and_changes_nothing(self):
        self.command(self.category, 0)
        before = list(MovementClassification.objects.values())
        for category in (self.category, self.other, None):
            self.assert_error("classification_revision_conflict",
                              category_id=category.pk if category else None)
            self.assertEqual(list(MovementClassification.objects.values()), before)
        self.command(None, 1)
        self.command(self.category, 2)
        self.assert_error("classification_revision_conflict", expected_revision=1)

    def test_absent_row_with_positive_revision_is_distinguished(self):
        self.assert_error("classification_not_present", expected_revision=1)
        self.assertFalse(MovementClassification.objects.exists())

    def test_invalid_and_unpersisted_selectors_are_safe_errors(self):
        for value in (None, str(self.movement.pk), 1, Movement()):
            self.assert_error("movement_id_invalid", movement_id=value)
        for value in (str(self.category.pk), 1, Category(display_name="Unsaved")):
            self.assert_error("category_id_invalid", category_id=value)
        for value in (None, True, -1, 1.0, "0", 2**63):
            self.assert_error("expected_revision_invalid", expected_revision=value)
        for value in (None, self.account.pk, Account(pk=self.account.pk)):
            self.assert_error("account_not_persisted", account=value)
        self.assert_error("movement_not_found", movement_id=Movement().pk)
        self.assert_error("category_not_found", category_id=Category().pk)
        other_movement = make_movement(label="other")
        self.assert_error("movement_not_found", movement_id=other_movement.pk)
        deleted = Account.objects.create(display_name="Synthetic deleted", kind="CURRENT",
                                        economic_orientation="ASSET", currency="CLP")
        Account.objects.filter(pk=deleted.pk).delete()
        self.assert_error("account_not_found", account=deleted)

    def test_inactive_existing_reference_noop_and_clear_allowed_new_assignments_rejected(self):
        original = self.command(self.category, 0)
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])
        self.assertEqual(self.command(self.category, 1), original)
        self.command(None, 1)
        self.assert_error("category_inactive", expected_revision=2)
        self.command(self.other, 2)
        self.assert_error("category_inactive", expected_revision=3)
        other_movement = make_movement(label="inactive")
        self.assert_error("category_inactive", account=other_movement.account,
                          movement_id=other_movement.pk)

    def test_rollback_of_initial_and_existing_change(self):
        for expected in (0, 1):
            before = list(MovementClassification.objects.values())
            with self.assertRaisesRegex(RuntimeError, "synthetic rollback"):
                with transaction.atomic():
                    self.command(self.other, expected)
                    raise RuntimeError("synthetic rollback")
            self.assertEqual(list(MovementClassification.objects.values()), before)
            if expected == 0:
                self.command(self.category, 0)

    def test_database_source_revision_and_cardinality_constraints(self):
        self.command(self.category, 0)
        for fields in ({"source": "AI"}, {"source": "RULE"}, {"source": "SYSTEM"},
                       {"source": "IMPORTED"}, {"revision": 0}, {"revision": -1}):
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                MovementClassification.objects.update(**fields)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovementClassification.objects.bulk_create([MovementClassification(
                movement=self.movement, category=self.other, source="MANUAL", updated_at=timezone.now()
            )])

    def test_model_save_validates_shape_and_rejects_reparenting(self):
        self.command(self.category, 0)
        other_movement = make_movement(label="reparent")
        for row in (MovementClassification.objects.get(),
                    MovementClassification.objects.only("movement").get()):
            row.movement = other_movement
            with self.assertRaises(ValidationError):
                row.save()
        for fields in ({"source": "AI"}, {"revision": 0},
                       {"updated_at": datetime(2026, 1, 1)}, {"updated_at": "invalid"}):
            row = MovementClassification.objects.get()
            for field, value in fields.items():
                setattr(row, field, value)
            with self.assertRaises(ValidationError):
                row.save()
        row = MovementClassification.objects.get()
        old_timestamp = row.updated_at
        row.save()
        row.refresh_from_db()
        self.assertEqual(row.updated_at, old_timestamp)

    def test_revision_exhaustion_fails_without_write(self):
        self.command(self.category, 0)
        MovementClassification.objects.update(revision=2**63 - 1)
        self.assert_error("classification_revision_exhausted", category_id=self.other.pk,
                          expected_revision=2**63 - 1)
        self.assertEqual(MovementClassification.objects.get().category_id, self.category.pk)

    def test_reporting_changes_only_classification_while_account_discovery_stays_exact(self):
        def read():
            def active(runtime):
                principal = account_access.trusted_local_principal_context()
                return (
                    report_canonical_movements(account=self.account,
                        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)),
                    account_access.list_read_accounts(principal_context=principal),
                    self.client.get("/api/v1/accounts/").json(),
                    self.client.get(f"/api/v1/accounts/{self.account.pk}/movements/",
                        {"start_date": "2026-01-01", "end_date": "2026-01-31"}).json(),
                )
            return local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1", port="8000", server_runner=active)
        before_report, *before_external = read()
        self.command(self.category, 0)
        assigned_report, *assigned_external = read()
        self.assertEqual(assigned_external[:2], before_external[:2])
        self.assertEqual(assigned_external[2]["movements"][0].pop("classification"), {
            "state": "CLASSIFIED", "category": {
                "id": str(self.category.pk), "display_name": self.category.display_name,
                "is_active": True,
            }, "revision": 1,
        })
        self.assertEqual(before_external[2]["movements"][0].pop("classification"), {
            "state": "NEVER_ASSIGNED", "category": None, "revision": 0,
        })
        self.assertEqual(assigned_external[2], before_external[2])
        self.assertEqual(assigned_report.movement_count, before_report.movement_count)
        self.assertEqual(assigned_report.net_signed_amount, before_report.net_signed_amount)
        self.assertEqual(
            assigned_report.movements[0].classification.state.value,
            "CLASSIFIED",
        )
        self.command(None, 1)
        cleared_report, *cleared_external = read()
        self.assertEqual(cleared_external[2]["movements"][0].pop("classification"), {
            "state": "CLEARED", "category": None, "revision": 2,
        })
        self.assertEqual(cleared_external, before_external)
        self.assertEqual(cleared_report.movement_count, before_report.movement_count)
        self.assertEqual(cleared_report.net_signed_amount, before_report.net_signed_amount)
        self.assertEqual(cleared_report.movements[0].classification.state.value, "CLEARED")
