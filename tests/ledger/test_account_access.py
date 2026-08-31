from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from unittest.mock import patch
from uuid import UUID, uuid4

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from gouda.ledger.models import (
    Account,
    FinancialObservation,
    ImportBatch,
    Movement,
    ObservationResolution,
    RawRecord,
    SourceArtifact,
)
from gouda.ledger.services import account_access
from gouda.ledger.services import movement_reporting


_UNSET = object()


class AccountAccessTests(TransactionTestCase):
    def setUp(self):
        self.principal = account_access.trusted_local_principal_context()
        self.account = self.make_account("Primary")
        self.other_account = self.make_account("Secondary")
        self.next_artifact = 1

    def make_account(self, label: str) -> Account:
        return Account.objects.create(
            display_name=f"Synthetic {label}",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="CLP",
        )

    def make_movement(
        self,
        *,
        account: Account | None = None,
        occurrence_date: date,
        signed_amount: str,
    ) -> Movement:
        account = account or self.account
        ordinal = self.next_artifact
        self.next_artifact += 1
        content = f"privacy-safe access artifact {ordinal}".encode()
        artifact = SourceArtifact.objects.create(
            original_filename=f"synthetic-access-{ordinal}.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="synthetic-access-v1",
            source_variant="synthetic_access_xlsx",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now(timezone.utc),
            reconciliation_status=ImportBatch.ReconciliationStatus.RECONCILED,
        )
        raw_record = RawRecord.objects.create(
            import_batch=batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=ordinal,
            row_number=ordinal,
            raw_cells=[],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            xlsx_amount_source_column="E",
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            parser_codes=[],
        )
        movement = Movement(
            raw_record=raw_record,
            account=account,
            occurrence_date=occurrence_date,
            signed_amount=Decimal(signed_amount),
            currency=account.currency,
            description="Synthetic canonical item",
        )
        movement.full_clean()
        movement.save()
        return movement

    def resolve(self, *, principal=_UNSET, selector=_UNSET) -> Account:
        return account_access.resolve_read_account(
            principal_context=self.principal if principal is _UNSET else principal,
            account_selector=self.account.pk if selector is _UNSET else selector,
        )

    def report(
        self,
        *,
        principal=_UNSET,
        selector=_UNSET,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    ):
        return account_access.report_authorized_canonical_movements(
            principal_context=self.principal if principal is _UNSET else principal,
            account_selector=self.account.pk if selector is _UNSET else selector,
            start_date=start_date,
            end_date=end_date,
        )

    def assert_access_error(self, code: str, function, /, *args, **kwargs) -> None:
        with self.assertRaises(account_access.AccountAccessServiceError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_recognized_principal_resolves_each_persisted_account(self):
        first = self.resolve()
        second = self.resolve(selector=self.other_account.pk)

        self.assertIsInstance(first, Account)
        self.assertFalse(first._state.adding)
        self.assertEqual(first.pk, self.account.pk)
        self.assertEqual(second.pk, self.other_account.pk)
        self.assertIsNot(first, self.account)

    def test_invalid_principal_context_fails_before_account_lookup(self):
        for invalid in (
            None,
            object(),
            "trusted-local-principal",
            account_access.TrustedPrincipalContext(),
            self.account,
            self.account.pk,
            {
                "source_kind": "synthetic_provider_source",
                "account_selector": self.account.pk,
            },
        ):
            with self.subTest(principal_type=type(invalid).__name__):
                with self.assertNumQueries(0):
                    self.assert_access_error(
                        "principal_context_invalid",
                        account_access.resolve_read_account,
                        principal_context=invalid,
                        account_selector=self.account.pk,
                    )

    def test_selector_requires_uuid_and_unknown_uuid_is_not_accessible(self):
        for invalid in (None, "", str(self.account.pk), 1, self.account):
            with self.subTest(selector_type=type(invalid).__name__):
                self.assert_access_error(
                    "account_selector_invalid",
                    self.resolve,
                    selector=invalid,
                )

        self.assert_access_error(
            "account_not_accessible",
            self.resolve,
            selector=uuid4(),
        )

    def test_account_uuid_possession_does_not_replace_principal_trust(self):
        self.assert_access_error(
            "principal_context_invalid",
            self.resolve,
            principal="trusted-local-principal",
            selector=self.account.pk,
        )

    def test_policy_denial_and_unknown_uuid_are_indistinguishable(self):
        unknown_id = uuid4()
        with patch.object(
            account_access,
            "_principal_may_read_account",
            return_value=False,
        ):
            for selector in (self.account.pk, unknown_id):
                with self.subTest(selector=selector):
                    self.assert_access_error(
                        "account_not_accessible",
                        self.resolve,
                        selector=selector,
                    )

        self.assertFalse(Account.objects.filter(pk=unknown_id).exists())

    def test_authorized_reporting_delegates_with_resolved_account(self):
        sentinel = object()
        with patch.object(
            account_access.movement_reporting,
            "report_canonical_movements",
            return_value=sentinel,
        ) as reporter:
            result = self.report(
                start_date=date(2026, 7, 2),
                end_date=date(2026, 7, 3),
            )

        self.assertIs(result, sentinel)
        values = reporter.call_args.kwargs
        self.assertIsInstance(values["account"], Account)
        self.assertEqual(values["account"].pk, self.account.pk)
        self.assertEqual(values["start_date"], date(2026, 7, 2))
        self.assertEqual(values["end_date"], date(2026, 7, 3))

    def test_authorized_report_reuses_existing_result_and_strictly_isolates_account(self):
        start = self.make_movement(
            occurrence_date=date(2026, 7, 1),
            signed_amount="10.25",
        )
        end = self.make_movement(
            occurrence_date=date(2026, 7, 31),
            signed_amount="-3.10",
        )
        self.make_movement(
            account=self.other_account,
            occurrence_date=date(2026, 7, 15),
            signed_amount="99.00",
        )

        result = self.report()

        self.assertIsInstance(result, movement_reporting.MovementReport)
        self.assertEqual(
            [item.movement_id for item in result.movements],
            [start.pk, end.pk],
        )
        self.assertEqual(result.movement_count, 2)
        self.assertEqual(result.net_signed_amount, Decimal("7.15"))
        self.assertEqual(result.account_id, self.account.pk)

    def test_reporting_date_failures_propagate_unchanged(self):
        cases = (
            ({"start_date": "2026-07-01"}, "start_date_invalid"),
            ({"end_date": datetime(2026, 7, 31)}, "end_date_invalid"),
            (
                {
                    "start_date": date(2026, 8, 1),
                    "end_date": date(2026, 7, 31),
                },
                "date_range_invalid",
            ),
        )
        for changes, code in cases:
            with self.subTest(code=code), self.assertRaises(
                movement_reporting.MovementReportingServiceError
            ) as caught:
                self.report(**changes)
            self.assertEqual(caught.exception.code, code)

    def test_account_disappearing_after_resolution_is_not_accessible(self):
        with patch.object(
            account_access.movement_reporting,
            "report_canonical_movements",
            side_effect=movement_reporting.MovementReportingServiceError(
                "account_not_found"
            ),
        ):
            self.assert_access_error(
                "account_not_accessible",
                self.report,
            )

    def test_report_does_not_broaden_provenance_or_principal_surface(self):
        self.make_movement(
            occurrence_date=date(2026, 7, 15),
            signed_amount="1.00",
        )

        serialized = asdict(self.report())

        self.assertEqual(
            set(serialized),
            {"account_id", "start_date", "end_date", "movements"},
        )
        self.assertEqual(
            set(serialized["movements"][0]["source_trace"]),
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
        rendered = repr(serialized)
        self.assertNotIn("principal", rendered.lower())
        self.assertNotIn("display_name", rendered)
        self.assertNotIn("raw_cells", rendered)
        self.assertNotIn("original_filename", rendered)
        self.assertNotIn("content_digest", rendered)

    def test_access_and_reporting_are_read_only_and_deterministic(self):
        self.make_movement(
            occurrence_date=date(2026, 7, 15),
            signed_amount="1.00",
        )
        tracked_models = (
            Account,
            SourceArtifact,
            ImportBatch,
            RawRecord,
            Movement,
            FinancialObservation,
            ObservationResolution,
        )
        before = {model: model.objects.count() for model in tracked_models}

        with CaptureQueriesContext(connection) as queries:
            first = self.report()
            second = self.report()

        after = {model: model.objects.count() for model in tracked_models}
        self.assertEqual(first, second)
        self.assertEqual(after, before)
        self.assertTrue(queries.captured_queries)
        self.assertTrue(
            all(
                query["sql"].lstrip().upper().startswith("SELECT")
                for query in queries.captured_queries
            )
        )
        self.assertTrue(all(isinstance(item.movement_id, UUID) for item in first.movements))
