from datetime import date, datetime
from decimal import Decimal
import hashlib
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
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


class ObservationResolutionServiceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic observation account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        content = b"synthetic observation artifact"
        self.artifact = SourceArtifact.objects.create(
            original_filename="synthetic-observation.xlsx",
            content_digest=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.batch = ImportBatch.objects.create(
            source_artifact=self.artifact,
            account=self.account,
            source_kind=ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
            parser_version="synthetic-observation-v1",
            source_variant="v1",
            status=ImportBatch.Status.ACCEPTED,
            completed_at=datetime.now().astimezone(),
            reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
        )
        self.next_ordinal = 1

    def make_raw(self):
        ordinal = self.next_ordinal
        self.next_ordinal += 1
        return RawRecord.objects.create(
            import_batch=self.batch,
            record_kind=RawRecord.RecordKind.SANTANDER_XLSX_ROW,
            record_ordinal=ordinal,
            row_number=ordinal,
            raw_cells=[
                {"column": "A", "value_kind": "string", "value": "01/02"}
            ],
            row_class=RawRecord.RowClass.MOVEMENT_CANDIDATE,
            parse_outcome=RawRecord.ParseOutcome.PARSED,
            xlsx_amount_source_column="E",
            parser_codes=[],
        )

    def make_observation(
        self,
        *,
        raw=None,
        transaction_date=date(2026, 2, 1),
        accounting_date=date(2026, 2, 2),
        signed_amount=Decimal("-10.00"),
        description="Synthetic purchase",
        source_reference="SYN-OBS-1",
        interpretation_method="synthetic_adapter",
        interpretation_version="v1",
        idempotency_key=None,
    ):
        raw = raw or self.make_raw()
        return service.create_financial_observation(
            raw_record_id=raw.pk,
            account_id=self.account.pk,
            transaction_date=transaction_date,
            accounting_date=accounting_date,
            signed_amount=signed_amount,
            currency="ZZZ",
            description=description,
            source_reference=source_reference,
            interpretation_method=interpretation_method,
            interpretation_version=interpretation_version,
            idempotency_key=idempotency_key or uuid.uuid4(),
        )

    def decision(self, *, key=None, reason="synthetic_decision"):
        return {
            "decision_source": ObservationResolution.DecisionSource.DETERMINISTIC_POLICY,
            "policy_name": "synthetic_policy",
            "policy_version": "v1",
            "reason_code": reason,
            "idempotency_key": key or uuid.uuid4(),
        }

    def confirm(self, observation, *, key=None, allow_exact_collision=False):
        return service.confirm_new(
            observation_id=observation.pk,
            occurrence_date=observation.accounting_date or observation.transaction_date,
            allow_exact_collision=allow_exact_collision,
            **self.decision(key=key, reason="synthetic_confirm"),
        )

    def test_valid_unresolved_observation_creation(self):
        observation = self.make_observation(
            description="  Synthetic purchase  ",
            source_reference="  SYN-OBS-1  ",
        )

        self.assertEqual(observation.state, FinancialObservation.State.UNRESOLVED)
        self.assertEqual(observation.state_version, 0)
        self.assertIsNone(observation.current_movement_id)
        self.assertEqual(observation.description, "Synthetic purchase")
        self.assertEqual(observation.source_reference, "SYN-OBS-1")
        self.assertFalse(observation.resolutions.exists())

    def test_creation_validates_exact_money_dates_currency_and_source_context(self):
        raw = self.make_raw()
        base = {
            "raw_record_id": raw.pk,
            "account_id": self.account.pk,
            "transaction_date": date(2026, 2, 1),
            "accounting_date": None,
            "signed_amount": Decimal("-10.00"),
            "currency": "ZZZ",
            "description": None,
            "source_reference": None,
            "interpretation_method": "synthetic_adapter",
            "interpretation_version": "v1",
        }
        invalid = (
            ({"transaction_date": None}, "financial_date_missing"),
            ({"signed_amount": Decimal("0.00")}, "signed_amount_zero"),
            ({"signed_amount": Decimal("1.001")}, "money_scale_exceeded"),
            ({"currency": "zz"}, "currency_invalid"),
            ({"transaction_date": datetime.now()}, "transaction_date_invalid"),
        )
        for changes, code in invalid:
            with self.subTest(code=code):
                values = {**base, **changes, "idempotency_key": uuid.uuid4()}
                with self.assertRaises(service.ObservationServiceError) as caught:
                    service.create_financial_observation(**values)
                self.assertEqual(caught.exception.code, code)
        self.assertFalse(FinancialObservation.objects.exists())

        other = Account.objects.create(
            display_name="Other synthetic account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        with self.assertRaises(service.ObservationServiceError) as caught:
            service.create_financial_observation(
                **{**base, "account_id": other.pk, "idempotency_key": uuid.uuid4()}
            )
        self.assertEqual(caught.exception.code, "raw_record_account_mismatch")

    def test_model_save_rejects_claim_mutation_and_service_changes_only_projection(self):
        observation = self.make_observation()
        original_claim = {
            field: getattr(observation, field)
            for field in FinancialObservation.IMMUTABLE_FIELD_ATTNAMES
        }
        observation.description = "Changed claim"
        with self.assertRaises(ValidationError):
            observation.save()

        resolution = service.reject(
            observation_id=observation.pk,
            **self.decision(reason="synthetic_reject"),
        )
        observation.refresh_from_db()
        self.assertEqual(resolution.action, ObservationResolution.Action.REJECT)
        for field, expected in original_claim.items():
            self.assertEqual(getattr(observation, field), expected)
        self.assertEqual(observation.state, FinancialObservation.State.REJECTED)
        self.assertEqual(observation.state_version, 1)

    def test_observation_creation_has_explicit_idempotency(self):
        raw = self.make_raw()
        key = uuid.uuid4()
        first = self.make_observation(raw=raw, idempotency_key=key)
        retry = self.make_observation(raw=raw, idempotency_key=key)
        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(FinancialObservation.objects.count(), 1)

        with self.assertRaises(service.ObservationServiceError) as caught:
            self.make_observation(
                raw=raw,
                description="Different interpretation",
                idempotency_key=key,
            )
        self.assertEqual(caught.exception.code, "observation_idempotency_conflict")

    def test_confirm_new_creates_one_canonical_movement_atomically(self):
        observation = self.make_observation()
        resolution = self.confirm(observation)
        observation.refresh_from_db()
        movement = Movement.objects.get()

        self.assertEqual(resolution.action, ObservationResolution.Action.CONFIRM_NEW)
        self.assertEqual(resolution.movement_id, movement.pk)
        self.assertEqual(observation.state, FinancialObservation.State.RESOLVED)
        self.assertEqual(observation.current_movement_id, movement.pk)
        self.assertEqual(observation.state_version, 1)
        self.assertEqual(movement.raw_record_id, observation.raw_record_id)
        self.assertEqual(movement.signed_amount, observation.signed_amount)
        self.assertEqual(movement.occurrence_date, observation.accounting_date)

    def test_second_observation_matches_same_movement_without_duplicate(self):
        first = self.make_observation()
        movement = self.confirm(first).movement
        second = self.make_observation()

        resolution = service.match_existing(
            observation_id=second.pk,
            movement_id=movement.pk,
            **self.decision(reason="synthetic_match"),
        )
        second.refresh_from_db()

        self.assertEqual(resolution.action, ObservationResolution.Action.MATCH_EXISTING)
        self.assertEqual(second.current_movement_id, movement.pk)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(movement.supporting_observations.count(), 2)

    def test_match_existing_treats_dates_and_text_as_policy_evidence(self):
        canonical = self.make_observation(
            description="Canonical synthetic description",
            source_reference="CANONICAL-REF",
        )
        movement = self.confirm(canonical).movement
        support = self.make_observation(
            transaction_date=date(2026, 3, 10),
            accounting_date=date(2026, 3, 12),
            description="Different source description",
            source_reference="DIFFERENT-REF",
        )

        resolution = service.match_existing(
            observation_id=support.pk,
            movement_id=movement.pk,
            **self.decision(reason="policy_selected_contextual_date_match"),
        )
        support.refresh_from_db()

        self.assertNotIn(
            movement.occurrence_date,
            {support.transaction_date, support.accounting_date},
        )
        self.assertNotEqual(support.description, movement.description)
        self.assertNotEqual(support.source_reference, movement.source_reference)
        self.assertEqual(resolution.action, ObservationResolution.Action.MATCH_EXISTING)
        self.assertEqual(support.current_movement_id, movement.pk)
        self.assertEqual(Movement.objects.count(), 1)

    def test_match_existing_rejects_account_currency_and_amount_incompatibility(self):
        canonical = self.make_observation()
        movement = self.confirm(canonical).movement

        amount_mismatch = self.make_observation(signed_amount=Decimal("-11.00"))
        with self.assertRaises(service.ObservationServiceError) as caught:
            service.match_existing(
                observation_id=amount_mismatch.pk,
                movement_id=movement.pk,
                **self.decision(reason="synthetic_amount_mismatch"),
            )
        self.assertEqual(caught.exception.code, "movement_amount_mismatch")

        other_account = Account.objects.create(
            display_name="Other synthetic match account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        other_content = b"synthetic other-account match artifact"
        other_artifact = SourceArtifact.objects.create(
            original_filename="synthetic-other-account.xlsx",
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
        other_movement = Movement.objects.create(
            raw_record=other_raw,
            account=other_account,
            occurrence_date=date(2026, 4, 1),
            signed_amount=Decimal("-10.00"),
            currency="ZZZ",
        )
        account_mismatch = self.make_observation()
        with self.assertRaises(service.ObservationServiceError) as caught:
            service.match_existing(
                observation_id=account_mismatch.pk,
                movement_id=other_movement.pk,
                **self.decision(reason="synthetic_account_mismatch"),
            )
        self.assertEqual(caught.exception.code, "movement_account_mismatch")

        currency_raw = self.make_raw()
        currency_movement = Movement.objects.create(
            raw_record=currency_raw,
            account=self.account,
            occurrence_date=date(2026, 4, 2),
            signed_amount=Decimal("-10.00"),
            currency="AAA",
        )
        currency_mismatch = self.make_observation()
        with self.assertRaises(service.ObservationServiceError) as caught:
            service.match_existing(
                observation_id=currency_mismatch.pk,
                movement_id=currency_movement.pk,
                **self.decision(reason="synthetic_currency_mismatch"),
            )
        self.assertEqual(caught.exception.code, "movement_currency_mismatch")

        for observation in (amount_mismatch, account_mismatch, currency_mismatch):
            observation.refresh_from_db()
            self.assertEqual(observation.state, FinancialObservation.State.UNRESOLVED)
            self.assertIsNone(observation.current_movement_id)

    def test_confirm_new_exact_collision_abstains_then_allows_explicit_distinct_event(self):
        first = self.make_observation(
            description="First synthetic purchase",
            source_reference="DISTINCT-1",
        )
        first_movement = self.confirm(first).movement
        second = self.make_observation(
            description="Second synthetic purchase",
            source_reference="DISTINCT-2",
        )
        initial_total = Movement.objects.filter(account=self.account).aggregate(
            total=models.Sum("signed_amount")
        )["total"]

        with self.assertRaises(service.ObservationServiceError) as caught:
            self.confirm(second)
        self.assertEqual(caught.exception.code, "movement_candidate_exists")
        second.refresh_from_db()
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(second.state, FinancialObservation.State.UNRESOLVED)
        self.assertIsNone(second.current_movement_id)
        self.assertFalse(second.resolutions.exists())
        self.assertEqual(
            Movement.objects.filter(account=self.account).aggregate(
                total=models.Sum("signed_amount")
            )["total"],
            initial_total,
        )

        resolution = self.confirm(second, allow_exact_collision=True)
        second.refresh_from_db()
        movements = list(Movement.objects.filter(account=self.account))

        self.assertEqual(resolution.action, ObservationResolution.Action.CONFIRM_NEW)
        self.assertNotEqual(resolution.movement_id, first_movement.pk)
        self.assertEqual(second.current_movement_id, resolution.movement_id)
        self.assertEqual(second.resolutions.count(), 1)
        self.assertEqual(len(movements), 2)
        self.assertEqual(
            {
                (
                    item.account_id,
                    item.occurrence_date,
                    item.signed_amount,
                    item.currency,
                )
                for item in movements
            },
            {
                (
                    self.account.pk,
                    first_movement.occurrence_date,
                    first_movement.signed_amount,
                    first_movement.currency,
                )
            },
        )
        self.assertEqual(
            {item.raw_record_id for item in movements},
            {first.raw_record_id, second.raw_record_id},
        )
        self.assertEqual(
            Movement.objects.filter(account=self.account).aggregate(
                total=models.Sum("signed_amount")
            )["total"],
            initial_total * 2,
        )

    def test_reject_and_reopen_are_audited(self):
        observation = self.make_observation()
        rejected = service.reject(
            observation_id=observation.pk,
            **self.decision(reason="synthetic_reject"),
        )
        reopened = service.reopen(
            observation_id=observation.pk,
            **self.decision(reason="synthetic_reopen"),
        )
        observation.refresh_from_db()

        self.assertEqual((rejected.sequence, reopened.sequence), (1, 2))
        self.assertEqual(reopened.from_state, FinancialObservation.State.REJECTED)
        self.assertEqual(observation.state, FinancialObservation.State.UNRESOLVED)
        self.assertEqual(observation.state_version, 2)

    def test_conflict_does_not_modify_movement_and_can_reopen(self):
        canonical = self.make_observation()
        movement = self.confirm(canonical).movement
        conflicting = self.make_observation(signed_amount=Decimal("-12.00"))
        before = (
            movement.occurrence_date,
            movement.signed_amount,
            movement.currency,
            movement.description,
            movement.source_reference,
        )

        conflict = service.mark_conflict(
            observation_id=conflicting.pk,
            movement_id=movement.pk,
            **self.decision(reason="synthetic_conflict"),
        )
        reopened = service.reopen(
            observation_id=conflicting.pk,
            **self.decision(reason="synthetic_reopen"),
        )
        conflicting.refresh_from_db()
        movement.refresh_from_db()

        self.assertEqual(conflict.to_state, FinancialObservation.State.CONFLICT)
        self.assertEqual(reopened.movement_id, movement.pk)
        self.assertEqual(conflicting.state, FinancialObservation.State.UNRESOLVED)
        self.assertIsNone(conflicting.current_movement_id)
        self.assertEqual(
            (
                movement.occurrence_date,
                movement.signed_amount,
                movement.currency,
                movement.description,
                movement.source_reference,
            ),
            before,
        )

    def test_supersede_requires_a_fresh_corrected_interpretation_and_is_terminal(self):
        raw = self.make_raw()
        predecessor = self.make_observation(raw=raw)
        successor = self.make_observation(
            raw=raw,
            description="Corrected synthetic purchase",
            idempotency_key=uuid.uuid4(),
        )
        resolution = service.supersede(
            observation_id=predecessor.pk,
            successor_observation_id=successor.pk,
            **self.decision(reason="synthetic_supersede"),
        )
        predecessor.refresh_from_db()
        successor.refresh_from_db()

        self.assertEqual(resolution.successor_observation_id, successor.pk)
        self.assertEqual(predecessor.state, FinancialObservation.State.SUPERSEDED)
        self.assertEqual(successor.state, FinancialObservation.State.UNRESOLVED)

        for command in (
            lambda: service.reopen(
                observation_id=predecessor.pk,
                **self.decision(reason="terminal_reopen"),
            ),
            lambda: service.reject(
                observation_id=predecessor.pk,
                **self.decision(reason="terminal_reject"),
            ),
        ):
            with self.assertRaises(service.ObservationServiceError) as caught:
                command()
            self.assertEqual(caught.exception.code, "observation_transition_invalid")

    def test_superseding_resolved_observation_preserves_canonical_movement(self):
        raw = self.make_raw()
        predecessor = self.make_observation(raw=raw)
        confirmed = self.confirm(predecessor)
        movement = confirmed.movement
        movement_before = (
            movement.raw_record_id,
            movement.account_id,
            movement.occurrence_date,
            movement.signed_amount,
            movement.currency,
            movement.description,
            movement.source_reference,
            movement.running_balance,
        )
        total_before = Movement.objects.filter(account=self.account).aggregate(
            total=models.Sum("signed_amount")
        )["total"]
        successor = self.make_observation(
            raw=raw,
            description="Corrected interpretation awaiting resolution",
        )

        superseded = service.supersede(
            observation_id=predecessor.pk,
            successor_observation_id=successor.pk,
            **self.decision(reason="synthetic_resolved_supersede"),
        )
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        movement.refresh_from_db()
        history = list(predecessor.resolutions.order_by("sequence"))

        self.assertEqual(predecessor.state, FinancialObservation.State.SUPERSEDED)
        self.assertIsNone(predecessor.current_movement_id)
        self.assertEqual(
            [item.action for item in history],
            [
                ObservationResolution.Action.CONFIRM_NEW,
                ObservationResolution.Action.SUPERSEDE,
            ],
        )
        self.assertEqual([item.movement_id for item in history], [movement.pk, movement.pk])
        self.assertEqual(superseded.movement_id, movement.pk)
        self.assertEqual(successor.state, FinancialObservation.State.UNRESOLVED)
        self.assertIsNone(successor.current_movement_id)
        self.assertFalse(successor.resolutions.exists())
        self.assertEqual(
            (
                movement.raw_record_id,
                movement.account_id,
                movement.occurrence_date,
                movement.signed_amount,
                movement.currency,
                movement.description,
                movement.source_reference,
                movement.running_balance,
            ),
            movement_before,
        )
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(
            Movement.objects.filter(account=self.account).aggregate(
                total=models.Sum("signed_amount")
            )["total"],
            total_before,
        )

    def test_unchanged_claim_cannot_be_successor(self):
        raw = self.make_raw()
        predecessor = self.make_observation(raw=raw)
        duplicate_claim = self.make_observation(raw=raw)
        with self.assertRaises(service.ObservationServiceError) as caught:
            service.supersede(
                observation_id=predecessor.pk,
                successor_observation_id=duplicate_claim.pk,
                **self.decision(reason="synthetic_supersede"),
            )
        self.assertEqual(caught.exception.code, "successor_claim_unchanged")

    def test_successor_cannot_be_reused_by_another_supersession(self):
        raw = self.make_raw()
        first_predecessor = self.make_observation(raw=raw, description="First interpretation")
        second_predecessor = self.make_observation(raw=raw, description="Second interpretation")
        successor = self.make_observation(raw=raw, description="Corrected interpretation")
        service.supersede(
            observation_id=first_predecessor.pk,
            successor_observation_id=successor.pk,
            **self.decision(reason="synthetic_first_supersede"),
        )

        with self.assertRaises(service.ObservationServiceError) as caught:
            service.supersede(
                observation_id=second_predecessor.pk,
                successor_observation_id=successor.pk,
                **self.decision(reason="synthetic_reused_successor"),
            )

        self.assertEqual(caught.exception.code, "successor_already_used")
        second_predecessor.refresh_from_db()
        self.assertEqual(second_predecessor.state, FinancialObservation.State.UNRESOLVED)

    def test_resolution_history_is_ordered_and_append_only(self):
        observation = self.make_observation()
        first = service.reject(
            observation_id=observation.pk,
            **self.decision(reason="synthetic_reject"),
        )
        service.reopen(
            observation_id=observation.pk,
            **self.decision(reason="synthetic_reopen"),
        )
        third = self.confirm(observation)
        history = list(observation.resolutions.order_by("sequence"))

        self.assertEqual([item.sequence for item in history], [1, 2, 3])
        first.reason_code = "changed_history"
        with self.assertRaises(ValidationError):
            first.save()
        with self.assertRaises(ValidationError):
            third.delete()
        self.assertEqual(observation.resolutions.count(), 3)

    def test_invalid_state_transitions_fail_without_history(self):
        observation = self.make_observation()
        self.confirm(observation)
        before = observation.resolutions.count()
        invalid_commands = (
            lambda: service.reject(
                observation_id=observation.pk,
                **self.decision(reason="invalid_reject"),
            ),
            lambda: service.confirm_new(
                observation_id=observation.pk,
                occurrence_date=observation.accounting_date,
                **self.decision(reason="invalid_confirm"),
            ),
        )
        for command in invalid_commands:
            with self.assertRaises(service.ObservationServiceError) as caught:
                command()
            self.assertEqual(caught.exception.code, "observation_transition_invalid")
        self.assertEqual(observation.resolutions.count(), before)

    def test_transition_table_is_explicit_and_complete(self):
        state = FinancialObservation.State
        action = ObservationResolution.Action
        self.assertEqual(
            service.OBSERVATION_TRANSITIONS,
            {
                action.CONFIRM_NEW: {state.UNRESOLVED: state.RESOLVED},
                action.MATCH_EXISTING: {state.UNRESOLVED: state.RESOLVED},
                action.REJECT: {state.UNRESOLVED: state.REJECTED},
                action.MARK_CONFLICT: {
                    state.UNRESOLVED: state.CONFLICT,
                    state.RESOLVED: state.CONFLICT,
                },
                action.REOPEN: {
                    state.REJECTED: state.UNRESOLVED,
                    state.CONFLICT: state.UNRESOLVED,
                },
                action.SUPERSEDE: {
                    state.UNRESOLVED: state.SUPERSEDED,
                    state.RESOLVED: state.SUPERSEDED,
                    state.REJECTED: state.SUPERSEDED,
                    state.CONFLICT: state.SUPERSEDED,
                },
            },
        )

    def test_resolution_retry_is_idempotent_and_conflicting_reuse_fails(self):
        observation = self.make_observation()
        key = uuid.uuid4()
        first = self.confirm(observation, key=key)
        retry = self.confirm(observation, key=key)
        self.assertEqual(retry.pk, first.pk)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(ObservationResolution.objects.count(), 1)

        with self.assertRaises(service.ObservationServiceError) as caught:
            service.reject(
                observation_id=observation.pk,
                **self.decision(key=key, reason="different_command"),
            )
        self.assertEqual(caught.exception.code, "resolution_idempotency_conflict")

    def test_unresolved_rejected_and_conflicted_observations_do_not_change_totals(self):
        canonical = self.make_observation(signed_amount=Decimal("25.00"))
        movement = self.confirm(canonical).movement
        expected_total = Movement.objects.filter(account=self.account).aggregate(
            total=models.Sum("signed_amount")
        )["total"]

        self.make_observation(signed_amount=Decimal("999.00"))
        rejected = self.make_observation(signed_amount=Decimal("888.00"))
        service.reject(
            observation_id=rejected.pk,
            **self.decision(reason="synthetic_reject"),
        )
        conflicted = self.make_observation(signed_amount=Decimal("777.00"))
        service.mark_conflict(
            observation_id=conflicted.pk,
            movement_id=movement.pk,
            **self.decision(reason="synthetic_conflict"),
        )

        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(
            Movement.objects.filter(account=self.account).aggregate(
                total=models.Sum("signed_amount")
            )["total"],
            expected_total,
        )

    def test_database_constraints_defend_observation_and_resolution_shapes(self):
        raw = self.make_raw()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinancialObservation.objects.create(
                    raw_record=raw,
                    account=self.account,
                    transaction_date=None,
                    accounting_date=None,
                    signed_amount=Decimal("1.00"),
                    currency="ZZZ",
                    interpretation_method="synthetic",
                    interpretation_version="v1",
                    idempotency_key=uuid.uuid4(),
                )

        observation = self.make_observation(raw=raw)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ObservationResolution.objects.create(
                    observation=observation,
                    sequence=1,
                    action=ObservationResolution.Action.REJECT,
                    from_state=FinancialObservation.State.UNRESOLVED,
                    to_state=FinancialObservation.State.RESOLVED,
                    movement=None,
                    successor_observation=None,
                    decision_source=ObservationResolution.DecisionSource.HUMAN,
                    policy_name="synthetic_policy",
                    policy_version="v1",
                    reason_code="invalid_shape",
                    idempotency_key=uuid.uuid4(),
                )
