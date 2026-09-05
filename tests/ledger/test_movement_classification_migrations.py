from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from tests.fixtures.movement_classification import make_movement


BEFORE = [("ledger", "0010_demo_synthetic_provenance")]
AFTER = [("ledger", "0011_movement_classification")]


class MovementClassificationMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        if targets == [("ledger", None)]:
            return None
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def tearDown(self):
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes("ledger"))
        finally:
            super().tearDown()

    def test_0010_upgrade_preserves_every_financial_and_provenance_field_no_backfill(self):
        apps = self.migrate(BEFORE)
        make_movement(apps=apps)
        names = ("Account", "Movement", "SourceArtifact", "ImportBatch", "RawRecord")
        before = {name: list(apps.get_model("ledger", name).objects.values()) for name in names}
        fields = {name: [(f.name, f.deconstruct()) for f in apps.get_model("ledger", name)._meta.fields]
                  for name in names}
        apps = self.migrate(AFTER)
        self.assertEqual(before, {name: list(apps.get_model("ledger", name).objects.values())
                                  for name in names})
        self.assertEqual(fields, {name: [(f.name, f.deconstruct()) for f in
                                        apps.get_model("ledger", name)._meta.fields] for name in names})
        self.assertFalse(apps.get_model("ledger", "Category").objects.exists())
        self.assertFalse(apps.get_model("ledger", "MovementClassification").objects.exists())

    def test_fresh_migration_path_and_database_expression_index(self):
        self.migrate([("ledger", None)])
        apps = self.migrate(AFTER)
        Category = apps.get_model("ledger", "Category")
        Category.objects.create(display_name="Groceries", is_active=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.create(display_name="GROCERIES")
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s",
                           ["category_display_name_ci_unique"])
            definition = cursor.fetchone()[0]
        self.assertIn("UNIQUE INDEX", definition)
        self.assertIn("lower(", definition)

    def test_reverse_refuses_category_data(self):
        apps = self.migrate(AFTER)
        Category = apps.get_model("ledger", "Category")
        category = Category.objects.create(display_name="Groceries")
        with self.assertRaisesRegex(RuntimeError, "while classification data exists"):
            self.migrate(BEFORE)
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_reverse_refuses_cleared_classification_without_any_categories(self):
        apps = self.migrate(AFTER)
        movement = make_movement(apps=apps)
        Classification = apps.get_model("ledger", "MovementClassification")
        Classification.objects.create(movement=movement, category=None, source="MANUAL",
                                      revision=2, updated_at=timezone.now())
        with self.assertRaisesRegex(RuntimeError, "while classification data exists"):
            self.migrate(BEFORE)
        self.assertEqual(Classification.objects.get().revision, 2)

    def test_empty_reverse_and_reapply(self):
        self.migrate(BEFORE)
        self.assertNotIn("ledger_category", connection.introspection.table_names())
        apps = self.migrate(AFTER)
        self.assertFalse(apps.get_model("ledger", "MovementClassification").objects.exists())
