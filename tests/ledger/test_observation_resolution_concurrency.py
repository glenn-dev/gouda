from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
import hashlib
from threading import Barrier
import uuid

from django.db import close_old_connections
from django.test import TransactionTestCase

from gouda.ledger.models import (
    Account,
    FinancialObservation,
    ImportBatch,
    Movement,
    ObservationResolution,
    RawRecord,
    SourceArtifact,
)
from gouda.ledger.services import observation_resolution as service


_WAIT_SECONDS = 15


class ObservationResolutionConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic concurrent observation account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        content = b"synthetic concurrent observation artifact"
        artifact = SourceArtifact.objects.create(
            original_filename="synthetic-concurrent-observation.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.batch = ImportBatch.objects.create(
            source_artifact=artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="synthetic-observation-v1",
            source_variant="v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now().astimezone(),
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        self.ordinal = 1

    def make_observation(self, *, raw=None, description="Synthetic candidate"):
        if raw is None:
            raw = RawRecord.objects.create(
                import_batch=self.batch,
                record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
                record_ordinal=self.ordinal,
                row_number=self.ordinal,
                raw_cells=[],
                row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
                parse_outcome=RawRecord.ParseOutcome.PARSED,
                xlsx_amount_source_column="E",
                parser_codes=[],
            )
            self.ordinal += 1
        return service.create_financial_observation(
            raw_record_id=raw.pk,
            account_id=self.account.pk,
            transaction_date=date(2026, 2, 1),
            accounting_date=date(2026, 2, 2),
            signed_amount=Decimal("-10.00"),
            currency="ZZZ",
            description=description,
            source_reference=None,
            interpretation_method="synthetic_adapter",
            interpretation_version="v1",
            idempotency_key=uuid.uuid4(),
        )

    def decision(self, key, reason):
        return {
            "decision_source": ObservationResolution.DecisionSource.DETERMINISTIC_POLICY,
            "policy_name": "synthetic_policy",
            "policy_version": "v1",
            "reason_code": reason,
            "idempotency_key": key,
        }

    def run_concurrently(self, callables):
        barrier = Barrier(len(callables))

        def worker(command):
            close_old_connections()
            try:
                barrier.wait(timeout=_WAIT_SECONDS)
                try:
                    result = command()
                    return ("ok", result.pk)
                except service.ObservationServiceError as error:
                    return ("error", error.code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(callables)) as executor:
            return list(executor.map(worker, callables))

    def test_same_observation_concurrent_resolution_has_one_winner(self):
        observation = self.make_observation()
        commands = [
            lambda key=uuid.uuid4(): service.confirm_new(
                observation_id=observation.pk,
                occurrence_date=date(2026, 2, 2),
                **self.decision(key, "concurrent_confirm"),
            )
            for _ in range(2)
        ]

        results = self.run_concurrently(commands)

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            [result[1] for result in results if result[0] == "error"],
            ["observation_transition_invalid"],
        )
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(ObservationResolution.objects.count(), 1)

    def test_same_account_competing_create_abstains_after_lock_reread(self):
        observations = [self.make_observation(), self.make_observation()]
        commands = [
            lambda observation=observation: service.confirm_new(
                observation_id=observation.pk,
                occurrence_date=date(2026, 2, 2),
                **self.decision(uuid.uuid4(), "competing_create"),
            )
            for observation in observations
        ]

        results = self.run_concurrently(commands)

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            [result[1] for result in results if result[0] == "error"],
            ["movement_candidate_exists"],
        )
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(
            FinancialObservation.objects.filter(
                state=FinancialObservation.State.RESOLVED
            ).count(),
            1,
        )

    def test_match_create_race_does_not_duplicate_existing_candidate(self):
        canonical = self.make_observation()
        movement = service.confirm_new(
            observation_id=canonical.pk,
            occurrence_date=date(2026, 2, 2),
            **self.decision(uuid.uuid4(), "canonical_seed"),
        ).movement
        support = self.make_observation()
        competing_create = self.make_observation()

        results = self.run_concurrently(
            [
                lambda: service.match_existing(
                    observation_id=support.pk,
                    movement_id=movement.pk,
                    **self.decision(uuid.uuid4(), "concurrent_match"),
                ),
                lambda: service.confirm_new(
                    observation_id=competing_create.pk,
                    occurrence_date=date(2026, 2, 2),
                    **self.decision(uuid.uuid4(), "concurrent_create"),
                ),
            ]
        )

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            [result[1] for result in results if result[0] == "error"],
            ["movement_candidate_exists"],
        )
        support.refresh_from_db()
        self.assertEqual(support.current_movement_id, movement.pk)
        self.assertEqual(Movement.objects.count(), 1)

    def test_concurrent_reject_reopen_preserves_a_valid_order(self):
        observation = self.make_observation()
        results = self.run_concurrently(
            [
                lambda: service.reject(
                    observation_id=observation.pk,
                    **self.decision(uuid.uuid4(), "concurrent_reject"),
                ),
                lambda: service.reopen(
                    observation_id=observation.pk,
                    **self.decision(uuid.uuid4(), "concurrent_reopen"),
                ),
            ]
        )
        observation.refresh_from_db()
        history = list(observation.resolutions.order_by("sequence"))

        self.assertEqual(history[0].action, ObservationResolution.Action.REJECT)
        if len(history) == 1:
            self.assertEqual(observation.state, FinancialObservation.State.REJECTED)
            self.assertIn(("error", "observation_transition_invalid"), results)
        else:
            self.assertEqual(
                [item.action for item in history],
                [ObservationResolution.Action.REJECT, ObservationResolution.Action.REOPEN],
            )
            self.assertEqual(observation.state, FinancialObservation.State.UNRESOLVED)

    def test_concurrent_supersession_has_one_terminal_successor(self):
        raw = RawRecord.objects.create(
            import_batch=self.batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=self.ordinal,
            row_number=self.ordinal,
            raw_cells=[],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            xlsx_amount_source_column="E",
            parser_codes=[],
        )
        predecessor = self.make_observation(raw=raw)
        successors = [
            self.make_observation(raw=raw, description=f"Corrected candidate {index}")
            for index in range(2)
        ]
        commands = [
            lambda successor=successor: service.supersede(
                observation_id=predecessor.pk,
                successor_observation_id=successor.pk,
                **self.decision(uuid.uuid4(), "concurrent_supersede"),
            )
            for successor in successors
        ]

        results = self.run_concurrently(commands)
        predecessor.refresh_from_db()

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            [result[1] for result in results if result[0] == "error"],
            ["observation_transition_invalid"],
        )
        self.assertEqual(predecessor.state, FinancialObservation.State.SUPERSEDED)
        self.assertEqual(predecessor.resolutions.count(), 1)

    def test_cross_account_supersession_rejects_before_incompatible_successor_lock(self):
        first = self.make_observation()
        other_account = Account.objects.create(
            display_name="Other synthetic concurrent account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        other_content = b"synthetic cross-account supersession artifact"
        other_artifact = SourceArtifact.objects.create(
            original_filename="synthetic-cross-account.xlsx",
            content_digest=hashlib.sha256(other_content).hexdigest(),
            content=other_content,
        )
        other_batch = ImportBatch.objects.create(
            source_artifact=other_artifact,
            account=other_account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="synthetic-observation-v1",
            source_variant="v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now().astimezone(),
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        other_raw = RawRecord.objects.create(
            import_batch=other_batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=1,
            row_number=1,
            raw_cells=[],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            xlsx_amount_source_column="E",
            parser_codes=[],
        )
        second = service.create_financial_observation(
            raw_record_id=other_raw.pk,
            account_id=other_account.pk,
            transaction_date=date(2026, 2, 1),
            accounting_date=date(2026, 2, 2),
            signed_amount=Decimal("-10.00"),
            currency="ZZZ",
            description="Other synthetic candidate",
            source_reference=None,
            interpretation_method="synthetic_adapter",
            interpretation_version="v1",
            idempotency_key=uuid.uuid4(),
        )

        results = self.run_concurrently(
            [
                lambda: service.supersede(
                    observation_id=first.pk,
                    successor_observation_id=second.pk,
                    **self.decision(uuid.uuid4(), "cross_account_supersede"),
                ),
                lambda: service.supersede(
                    observation_id=second.pk,
                    successor_observation_id=first.pk,
                    **self.decision(uuid.uuid4(), "cross_account_supersede"),
                ),
            ]
        )

        self.assertCountEqual(
            results,
            [
                ("error", "successor_account_mismatch"),
                ("error", "successor_account_mismatch"),
            ],
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.state, FinancialObservation.State.UNRESOLVED)
        self.assertEqual(second.state, FinancialObservation.State.UNRESOLVED)
        self.assertFalse(ObservationResolution.objects.exists())

    def test_duplicate_idempotency_key_execution_returns_one_resolution(self):
        observation = self.make_observation()
        key = uuid.uuid4()
        commands = [
            lambda: service.confirm_new(
                observation_id=observation.pk,
                occurrence_date=date(2026, 2, 2),
                **self.decision(key, "idempotent_concurrent_confirm"),
            )
            for _ in range(2)
        ]

        results = self.run_concurrently(commands)

        self.assertTrue(all(result[0] == "ok" for result in results))
        self.assertEqual(len({result[1] for result in results}), 1)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(ObservationResolution.objects.count(), 1)
