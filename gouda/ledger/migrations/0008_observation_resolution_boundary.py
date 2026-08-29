import django.db.models.deletion
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [("ledger", "0007_santander_tdc_account_binding")]

    operations = [
        migrations.CreateModel(
            name="FinancialObservation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("transaction_date", models.DateField(blank=True, null=True)),
                ("accounting_date", models.DateField(blank=True, null=True)),
                ("signed_amount", models.DecimalField(decimal_places=2, max_digits=20)),
                ("currency", models.CharField(max_length=3)),
                ("description", models.TextField(blank=True, null=True)),
                ("source_reference", models.TextField(blank=True, null=True)),
                ("interpretation_method", models.CharField(max_length=64)),
                ("interpretation_version", models.CharField(max_length=64)),
                ("idempotency_key", models.UUIDField(unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("UNRESOLVED", "Unresolved"),
                            ("RESOLVED", "Resolved"),
                            ("REJECTED", "Rejected"),
                            ("CONFLICT", "Conflict"),
                            ("SUPERSEDED", "Superseded"),
                        ],
                        default="UNRESOLVED",
                        max_length=12,
                    ),
                ),
                ("state_version", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_observations",
                        to="ledger.account",
                    ),
                ),
                (
                    "current_movement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supporting_observations",
                        to="ledger.movement",
                    ),
                ),
                (
                    "raw_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="financial_observations",
                        to="ledger.rawrecord",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["account", "transaction_date"],
                        name="observation_account_tx_idx",
                    ),
                    models.Index(
                        fields=["account", "accounting_date"],
                        name="observation_account_acct_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=~models.Q(signed_amount=0),
                        name="observation_signed_amount_nonzero",
                    ),
                    models.CheckConstraint(
                        check=models.Q(currency__regex="^[A-Z]{3}$"),
                        name="observation_currency_iso_like",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(transaction_date__isnull=False)
                            | models.Q(accounting_date__isnull=False)
                        ),
                        name="observation_financial_date_present",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            state__in=[
                                "UNRESOLVED",
                                "RESOLVED",
                                "REJECTED",
                                "CONFLICT",
                                "SUPERSEDED",
                            ]
                        ),
                        name="observation_state_known",
                    ),
                    models.CheckConstraint(
                        check=(
                            ~models.Q(interpretation_method="")
                            & ~models.Q(interpretation_version="")
                        ),
                        name="observation_interpreter_nonempty",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(
                                state__in=["RESOLVED", "CONFLICT"],
                                current_movement__isnull=False,
                            )
                            | models.Q(
                                state__in=["UNRESOLVED", "REJECTED", "SUPERSEDED"],
                                current_movement__isnull=True,
                            )
                        ),
                        name="observation_state_movement_shape",
                    ),
                    models.CheckConstraint(
                        check=models.Q(state_version__gte=0),
                        name="observation_state_version_nonnegative",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ObservationResolution",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("sequence", models.PositiveIntegerField()),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CONFIRM_NEW", "Confirm as new Movement"),
                            ("MATCH_EXISTING", "Match existing Movement"),
                            ("REJECT", "Reject"),
                            ("MARK_CONFLICT", "Mark conflict"),
                            ("REOPEN", "Reopen"),
                            ("SUPERSEDE", "Supersede"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "from_state",
                    models.CharField(
                        choices=[
                            ("UNRESOLVED", "Unresolved"),
                            ("RESOLVED", "Resolved"),
                            ("REJECTED", "Rejected"),
                            ("CONFLICT", "Conflict"),
                            ("SUPERSEDED", "Superseded"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "to_state",
                    models.CharField(
                        choices=[
                            ("UNRESOLVED", "Unresolved"),
                            ("RESOLVED", "Resolved"),
                            ("REJECTED", "Rejected"),
                            ("CONFLICT", "Conflict"),
                            ("SUPERSEDED", "Superseded"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "decision_source",
                    models.CharField(
                        choices=[
                            ("DETERMINISTIC_POLICY", "Deterministic policy"),
                            ("HUMAN", "Human"),
                        ],
                        max_length=24,
                    ),
                ),
                ("policy_name", models.CharField(max_length=64)),
                ("policy_version", models.CharField(max_length=64)),
                ("reason_code", models.CharField(max_length=64)),
                ("idempotency_key", models.UUIDField(unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "movement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="observation_resolutions",
                        to="ledger.movement",
                    ),
                ),
                (
                    "observation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="resolutions",
                        to="ledger.financialobservation",
                    ),
                ),
                (
                    "successor_observation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="superseding_resolutions",
                        to="ledger.financialobservation",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("observation", "sequence"),
                        name="one_resolution_per_observation_sequence",
                    ),
                    models.CheckConstraint(
                        check=models.Q(sequence__gt=0),
                        name="resolution_sequence_positive",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            action__in=[
                                "CONFIRM_NEW",
                                "MATCH_EXISTING",
                                "REJECT",
                                "MARK_CONFLICT",
                                "REOPEN",
                                "SUPERSEDE",
                            ]
                        ),
                        name="resolution_action_known",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            decision_source__in=["DETERMINISTIC_POLICY", "HUMAN"]
                        ),
                        name="resolution_decision_source_known",
                    ),
                    models.CheckConstraint(
                        check=(
                            ~models.Q(policy_name="")
                            & ~models.Q(policy_version="")
                            & ~models.Q(reason_code="")
                        ),
                        name="resolution_required_text_nonempty",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(
                                action__in=["CONFIRM_NEW", "MATCH_EXISTING"],
                                from_state="UNRESOLVED",
                                to_state="RESOLVED",
                                movement__isnull=False,
                                successor_observation__isnull=True,
                            )
                            | models.Q(
                                action="REJECT",
                                from_state="UNRESOLVED",
                                to_state="REJECTED",
                                movement__isnull=True,
                                successor_observation__isnull=True,
                            )
                            | models.Q(
                                action="MARK_CONFLICT",
                                from_state__in=["UNRESOLVED", "RESOLVED"],
                                to_state="CONFLICT",
                                movement__isnull=False,
                                successor_observation__isnull=True,
                            )
                            | models.Q(
                                action="REOPEN",
                                from_state="REJECTED",
                                to_state="UNRESOLVED",
                                movement__isnull=True,
                                successor_observation__isnull=True,
                            )
                            | models.Q(
                                action="REOPEN",
                                from_state="CONFLICT",
                                to_state="UNRESOLVED",
                                movement__isnull=False,
                                successor_observation__isnull=True,
                            )
                            | models.Q(
                                action="SUPERSEDE",
                                from_state__in=["UNRESOLVED", "REJECTED"],
                                to_state="SUPERSEDED",
                                movement__isnull=True,
                                successor_observation__isnull=False,
                            )
                            | models.Q(
                                action="SUPERSEDE",
                                from_state__in=["RESOLVED", "CONFLICT"],
                                to_state="SUPERSEDED",
                                movement__isnull=False,
                                successor_observation__isnull=False,
                            )
                        ),
                        name="resolution_transition_shape",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(successor_observation__isnull=True)
                            | ~models.Q(successor_observation=models.F("observation"))
                        ),
                        name="resolution_successor_not_self",
                    ),
                ],
            },
        ),
    ]
