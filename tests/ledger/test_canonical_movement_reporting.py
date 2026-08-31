from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from unittest.mock import patch
from uuid import uuid4

from django.test import TransactionTestCase

from gouda.bci_historical_pdf import parse_bci_historical_pdf
from gouda.ledger.models import (
    Account,
    FinancialObservation,
    ImportBatch,
    Movement,
    ObservationResolution,
    RawRecord,
    SourceArtifact,
)
from gouda.ledger.services import movement_reporting as reporting
from gouda.ledger.services import observation_resolution, santander_import
from gouda.ledger.services import santander_tdc_import
from gouda.ledger.services.bci_historical_import import (
    import_bci_historical_current_account_pdf,
)
from gouda.ledger.services.bci_historical_policy import (
    resolve_bci_historical_batch,
)
from tests.fixtures.bci_historical import synthetic_bci_historical_pdf
from tests.ledger.test_santander_tdc_evidence import synthetic_result
from tests.test_santander_parser import workbook_bytes


class MovementReportingTests(TransactionTestCase):
    def setUp(self):
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

    def make_source(
        self,
        *,
        account: Account | None = None,
        source_kind: str = ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
        source_variant: str = "synthetic_variant",
        parser_version: str = "synthetic-parser-v1",
        reconciliation_status: str = ImportBatch.ReconciliationStatus.RECONCILED,
    ) -> tuple[ImportBatch, RawRecord]:
        account = account or self.account
        ordinal = self.next_artifact
        self.next_artifact += 1
        content = f"privacy-safe synthetic artifact {ordinal}".encode()
        artifact = SourceArtifact.objects.create(
            original_filename=f"synthetic-{ordinal}.dat",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=account,
            source_kind=source_kind,
            parser_version=parser_version,
            source_variant=source_variant,
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
                        "value": "synthetic private payload marker",
                    }
                ],
                row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
                xlsx_amount_source_column="E",
            )
        return batch, RawRecord.objects.create(**raw_values)

    def make_movement(
        self,
        *,
        account: Account | None = None,
        occurrence_date: date = date(2026, 4, 15),
        signed_amount: Decimal = Decimal("1.00"),
        description: str | None = "Synthetic canonical description",
        source_kind: str = ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
        source_variant: str = "synthetic_variant",
        parser_version: str = "synthetic-parser-v1",
        reconciliation_status: str = ImportBatch.ReconciliationStatus.RECONCILED,
    ) -> Movement:
        account = account or self.account
        _, raw = self.make_source(
            account=account,
            source_kind=source_kind,
            source_variant=source_variant,
            parser_version=parser_version,
            reconciliation_status=reconciliation_status,
        )
        movement = Movement(
            raw_record=raw,
            account=account,
            occurrence_date=occurrence_date,
            signed_amount=signed_amount,
            currency=account.currency,
            description=description,
        )
        movement.full_clean()
        movement.save()
        return movement

    def report(self, *, account=None, start=date(2026, 4, 1), end=date(2026, 4, 30)):
        return reporting.report_canonical_movements(
            account=account or self.account,
            start_date=start,
            end_date=end,
        )

    def decision(self) -> dict[str, object]:
        return {
            "decision_source": ObservationResolution.DecisionSource.DETERMINISTIC_POLICY,
            "policy_name": "synthetic_reporting_policy",
            "policy_version": "v1",
            "reason_code": "synthetic_reporting_decision",
            "idempotency_key": uuid4(),
        }

    def make_observation(self, raw: RawRecord, *, amount: str, version: str):
        return observation_resolution.create_financial_observation(
            raw_record_id=raw.pk,
            account_id=self.account.pk,
            transaction_date=None,
            accounting_date=date(2026, 4, 15),
            signed_amount=Decimal(amount),
            currency=self.account.currency,
            description="Synthetic observation description",
            source_reference="SYNTHETIC-OBSERVATION",
            interpretation_method="synthetic_reporting_adapter",
            interpretation_version=version,
            idempotency_key=uuid4(),
        )

    def test_inclusive_period_account_isolation_exact_total_and_count(self):
        start = self.make_movement(
            occurrence_date=date(2026, 4, 1),
            signed_amount=Decimal("10.25"),
        )
        middle = self.make_movement(
            occurrence_date=date(2026, 4, 15),
            signed_amount=Decimal("-3.10"),
        )
        end = self.make_movement(
            occurrence_date=date(2026, 4, 30),
            signed_amount=Decimal("0.05"),
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

        report = self.report()

        self.assertEqual(report.account_id, self.account.pk)
        self.assertEqual((report.start_date, report.end_date), (date(2026, 4, 1), date(2026, 4, 30)))
        self.assertEqual(
            [item.movement_id for item in report.movements],
            [start.pk, middle.pk, end.pk],
        )
        self.assertEqual(report.movement_count, 3)
        self.assertEqual(report.net_signed_amount, Decimal("7.20"))
        self.assertEqual(
            report.net_signed_amount,
            sum((item.signed_amount for item in report.movements), Decimal("0.00")),
        )

    def test_empty_period_has_exact_zero_and_no_movements(self):
        report = self.report(start=date(2026, 6, 1), end=date(2026, 6, 30))
        self.assertEqual(report.movements, ())
        self.assertEqual(report.movement_count, 0)
        self.assertEqual(report.net_signed_amount, Decimal("0.00"))

    def test_invalid_account_and_dates_fail_with_stable_codes(self):
        cases = (
            ({"account": Account()}, "account_not_persisted"),
            ({"start_date": datetime(2026, 4, 1)}, "start_date_invalid"),
            ({"end_date": "2026-04-30"}, "end_date_invalid"),
            (
                {"start_date": date(2026, 5, 1), "end_date": date(2026, 4, 30)},
                "date_range_invalid",
            ),
        )
        for changes, code in cases:
            values = {
                "account": self.account,
                "start_date": date(2026, 4, 1),
                "end_date": date(2026, 4, 30),
                **changes,
            }
            with self.subTest(code=code), self.assertRaises(
                reporting.MovementReportingServiceError
            ) as caught:
                reporting.report_canonical_movements(**values)
            self.assertEqual(caught.exception.code, code)

        deleted = self.make_account("Deleted")
        deleted_id = deleted.pk
        deleted.delete()
        deleted.pk = deleted_id
        deleted._state.adding = False
        with self.assertRaises(reporting.MovementReportingServiceError) as caught:
            self.report(account=deleted)
        self.assertEqual(caught.exception.code, "account_not_found")

    def test_same_date_order_uses_movement_uuid_tie_breaker_deterministically(self):
        movements = [
            self.make_movement(
                occurrence_date=date(2026, 4, 10),
                signed_amount=Decimal(str(value)),
            )
            for value in ("3.00", "1.00", "2.00")
        ]
        expected = sorted((movement.pk for movement in movements))

        first = self.report()
        second = self.report()

        self.assertEqual([item.movement_id for item in first.movements], expected)
        self.assertEqual(first, second)

    def test_safe_provenance_is_complete_and_avoids_source_payloads(self):
        movement = self.make_movement(
            source_variant="synthetic_safe_variant",
            parser_version="synthetic-safe-v1",
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        item = self.report().movements[0]
        batch = movement.raw_record.import_batch
        trace = item.source_trace

        self.assertEqual(trace.raw_record_id, movement.raw_record_id)
        self.assertEqual(trace.import_batch_id, batch.pk)
        self.assertEqual(trace.source_artifact_id, batch.source_artifact_id)
        self.assertEqual(trace.source_kind, batch.source_kind)
        self.assertEqual(trace.source_variant, "synthetic_safe_variant")
        self.assertEqual(trace.parser_version, "synthetic-safe-v1")
        self.assertEqual(trace.import_status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(trace.reconciliation_status, ImportBatch.ReconciliationStatus.NOT_APPLICABLE)
        self.assertEqual(item.description, movement.description)

        serialized = asdict(item)
        self.assertEqual(
            set(serialized["source_trace"]),
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
        self.assertNotIn("description", serialized["source_trace"])
        rendered = repr(serialized)
        self.assertNotIn("synthetic private payload marker", rendered)
        self.assertNotIn(batch.source_artifact.original_filename, rendered)
        self.assertNotIn(batch.source_artifact.content_digest, rendered)
        self.assertNotIn("raw_cells", rendered)
        self.assertNotIn("source_reference", rendered)
        self.assertNotIn("running_balance", rendered)

    def test_report_is_source_neutral_across_canonical_write_routes(self):
        current = self.make_movement(
            occurrence_date=date(2026, 4, 1),
            signed_amount=Decimal("5.00"),
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            source_variant="santander_current_account_xlsx",
        )
        tdc_account = self.make_account("Card", liability=True)
        tdc = self.make_movement(
            account=tdc_account,
            occurrence_date=date(2026, 4, 2),
            signed_amount=Decimal("-7.00"),
            source_kind=ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
            source_variant="santander_credit_card_pdf",
        )
        historical = self.make_movement(
            occurrence_date=date(2026, 4, 3),
            signed_amount=Decimal("8.00"),
            source_kind=ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF,
            source_variant="bci_historical_current_account_pdf",
        )

        current_report = self.report()
        tdc_report = self.report(account=tdc_account)

        self.assertEqual(
            [item.movement_id for item in current_report.movements],
            [current.pk, historical.pk],
        )
        self.assertEqual(
            [item.source_trace.source_kind for item in current_report.movements],
            [
                ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF,
            ],
        )
        self.assertEqual(tdc_report.movements[0].movement_id, tdc.pk)
        self.assertEqual(tdc_report.movements[0].signed_amount, Decimal("-7.00"))

    def test_santander_current_account_imported_movements_are_reported(self):
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

        report = self.report()

        self.assertEqual(report.movement_count, 2)
        self.assertEqual(report.net_signed_amount, Decimal("1.00"))
        self.assertTrue(
            all(
                item.source_trace.import_batch_id == batch.pk
                and item.source_trace.source_kind
                == ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX
                for item in report.movements
            )
        )

    def test_santander_tdc_imported_canonical_sign_is_reported_unchanged(self):
        account = self.make_account("Imported card", liability=True)
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

        report = self.report(
            account=account,
            start=date(2026, 6, 1),
            end=date(2026, 6, 30),
        )

        self.assertEqual(report.movement_count, 1)
        self.assertEqual(report.movements[0].signed_amount, Decimal("-22303.00"))
        self.assertEqual(report.net_signed_amount, Decimal("-22303.00"))
        self.assertEqual(report.movements[0].source_trace.import_batch_id, batch.pk)
        self.assertEqual(
            report.movements[0].source_trace.source_kind,
            ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
        )

    def test_observation_states_do_not_add_or_filter_canonical_movements(self):
        _, unresolved_raw = self.make_source()
        self.make_observation(unresolved_raw, amount="-1.00", version="unresolved-v1")

        _, rejected_raw = self.make_source()
        rejected = self.make_observation(rejected_raw, amount="-2.00", version="rejected-v1")
        observation_resolution.reject(observation_id=rejected.pk, **self.decision())

        _, superseded_raw = self.make_source()
        predecessor = self.make_observation(superseded_raw, amount="-3.00", version="old-v1")
        successor = self.make_observation(superseded_raw, amount="-4.00", version="new-v1")
        observation_resolution.supersede(
            observation_id=predecessor.pk,
            successor_observation_id=successor.pk,
            **self.decision(),
        )

        canonical = self.make_movement(signed_amount=Decimal("9.00"))

        report = self.report()
        self.assertEqual([item.movement_id for item in report.movements], [canonical.pk])
        self.assertEqual(FinancialObservation.objects.count(), 4)

    def test_bci_historical_enters_report_only_after_canonical_resolution(self):
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

        self.assertEqual(self.report().movements, ())
        resolutions = resolve_bci_historical_batch(import_batch_id=batch.pk)
        report = self.report()

        self.assertEqual(len(resolutions), 1)
        self.assertEqual(report.movement_count, 1)
        self.assertEqual(
            report.movements[0].source_trace.source_kind,
            ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF,
        )

    def test_superseding_originating_observation_does_not_retract_movement(self):
        _, raw = self.make_source()
        predecessor = self.make_observation(raw, amount="-6.00", version="confirmed-v1")
        resolution = observation_resolution.confirm_new(
            observation_id=predecessor.pk,
            occurrence_date=predecessor.accounting_date,
            **self.decision(),
        )
        successor = self.make_observation(raw, amount="-5.00", version="successor-v1")
        observation_resolution.supersede(
            observation_id=predecessor.pk,
            successor_observation_id=successor.pk,
            **self.decision(),
        )

        report = self.report()
        self.assertEqual([item.movement_id for item in report.movements], [resolution.movement_id])
        self.assertEqual(report.net_signed_amount, Decimal("-6.00"))

    def test_provenance_loading_avoids_n_plus_one_queries(self):
        for value in ("1.00", "2.00", "3.00"):
            self.make_movement(signed_amount=Decimal(value))

        with self.assertNumQueries(2):
            report = self.report()
            tuple(asdict(item) for item in report.movements)
