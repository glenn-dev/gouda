"""Minimal relational model for the Gouda import/persistence boundary."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from .validation import validate_exact_money


class Account(models.Model):
    class Kind(models.TextChoices):
        CURRENT = "CURRENT", "Current account"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    currency = models.CharField(max_length=3)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(currency__regex=r"^[A-Z]{3}$"),
                name="account_currency_iso_like",
            ),
        ]

    def __str__(self) -> str:
        return f"Account {self.pk}"


class SourceArtifact(models.Model):
    class SourceKind(models.TextChoices):
        SANTANDER_CURRENT_ACCOUNT_XLSX = (
            "SANTANDER_CURRENT_ACCOUNT_XLSX",
            "Santander current-account XLSX",
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_kind = models.CharField(max_length=64, choices=SourceKind.choices)
    original_filename = models.CharField(max_length=255)
    content_digest = models.CharField(max_length=64, unique=True)
    content = models.BinaryField(editable=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(content_digest__regex=r"^[0-9a-f]{64}$"),
                name="artifact_sha256_hex",
            ),
        ]


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "Processing"
        ACCEPTED = "ACCEPTED", "Accepted"
        PARTIAL = "PARTIAL", "Partial"
        REJECTED = "REJECTED", "Rejected"
        FATAL = "FATAL", "Fatal"
        DUPLICATE = "DUPLICATE", "Duplicate"

    class ReconciliationStatus(models.TextChoices):
        RECONCILED = "RECONCILED", "Reconciled"
        NOT_RECONCILED = "NOT_RECONCILED", "Not reconciled"
        INSUFFICIENT_DATA = "INSUFFICIENT_DATA", "Insufficient data"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"

    class FailureStage(models.TextChoices):
        PARSER = "PARSER", "Parser"
        PERSISTENCE = "PERSISTENCE", "Persistence"
        BOUNDARY = "BOUNDARY", "Boundary"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_artifact = models.ForeignKey(SourceArtifact, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    parser_version = models.CharField(max_length=64)
    source_variant = models.CharField(max_length=32, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="duplicate_attempts",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    sheet_alias = models.CharField(max_length=16, null=True, blank=True)
    worksheet_name = models.CharField(max_length=255, null=True, blank=True)
    worksheet_ordinal = models.PositiveSmallIntegerField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    parsed_count = models.PositiveIntegerField(default=0)
    ignored_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    reconciliation_status = models.CharField(
        max_length=24,
        choices=ReconciliationStatus.choices,
        null=True,
        blank=True,
    )
    opening_balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    ending_balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    reconciliation_difference = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    failure_stage = models.CharField(max_length=16, choices=FailureStage.choices, null=True, blank=True)
    failure_code = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(status__in=["PROCESSING", "ACCEPTED", "PARTIAL", "REJECTED", "FATAL", "DUPLICATE"]),
                name="batch_status_known",
            ),
            models.CheckConstraint(
                check=Q(source_variant__isnull=True) | ~Q(source_variant=""),
                name="batch_source_variant_not_empty",
            ),
            models.CheckConstraint(
                check=(
                    Q(status__in=["PROCESSING", "FATAL"])
                    | Q(
                        status__in=["ACCEPTED", "PARTIAL", "REJECTED", "DUPLICATE"],
                        source_variant__isnull=False,
                    )
                ),
                name="batch_source_variant_matches_status",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="PROCESSING", completed_at__isnull=True)
                    | Q(status__in=["ACCEPTED", "PARTIAL", "REJECTED", "FATAL", "DUPLICATE"], completed_at__isnull=False)
                ),
                name="batch_completion_matches_status",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="DUPLICATE", duplicate_of__isnull=False)
                    | Q(status__in=["PROCESSING", "ACCEPTED", "PARTIAL", "REJECTED", "FATAL"], duplicate_of__isnull=True)
                ),
                name="batch_duplicate_reference_matches_status",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="FATAL", failure_stage__isnull=False, failure_code__isnull=False)
                    | Q(status__in=["PROCESSING", "ACCEPTED", "PARTIAL", "REJECTED", "DUPLICATE"], failure_stage__isnull=True, failure_code__isnull=True)
                ),
                name="batch_failure_fields_match_status",
            ),
            models.CheckConstraint(
                check=Q(period_start__isnull=True) | Q(period_end__isnull=True) | Q(period_start__lte=F("period_end")),
                name="batch_period_order",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="PROCESSING", reconciliation_status__isnull=True)
                    | Q(status="FATAL", reconciliation_status__isnull=True)
                    | Q(status="DUPLICATE", reconciliation_status__isnull=True)
                    | Q(status__in=["ACCEPTED", "PARTIAL", "REJECTED"], reconciliation_status__isnull=False)
                ),
                name="batch_reconciliation_matches_status",
            ),
            models.CheckConstraint(
                check=Q(parsed_count__gte=0) & Q(ignored_count__gte=0) & Q(rejected_count__gte=0),
                name="batch_counts_nonnegative",
            ),
            models.CheckConstraint(
                check=(
                    Q(status="ACCEPTED", rejected_count=0)
                    | Q(status="PARTIAL", parsed_count__gt=0, rejected_count__gt=0)
                    | Q(status="REJECTED", parsed_count=0, rejected_count__gt=0)
                    | Q(status="FATAL", parsed_count=0, ignored_count=0, rejected_count=0)
                    | Q(status="DUPLICATE", parsed_count=0, ignored_count=0, rejected_count=0)
                    | Q(status="PROCESSING")
                ),
                name="batch_counts_match_status",
            ),
            models.CheckConstraint(
                check=Q(duplicate_of__isnull=True) | ~Q(duplicate_of=F("id")),
                name="batch_duplicate_not_self",
            ),
            models.UniqueConstraint(
                fields=["source_artifact", "account"],
                condition=Q(status__in=["ACCEPTED", "PARTIAL", "REJECTED"]),
                name="one_materialized_batch_per_artifact_account",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        for field_name in ("opening_balance", "ending_balance", "reconciliation_difference"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages

        if self.status == self.Status.DUPLICATE:
            if self.duplicate_of_id == self.id:
                errors["duplicate_of"] = ["A batch cannot duplicate itself."]
                target = None
            else:
                try:
                    target = self.duplicate_of
                except ImportBatch.DoesNotExist:
                    target = None
            if target is None and "duplicate_of" not in errors:
                errors["duplicate_of"] = ["A duplicate batch must reference a materialized batch."]
            elif target is not None and target.status not in {
                self.Status.ACCEPTED,
                self.Status.PARTIAL,
                self.Status.REJECTED,
            }:
                errors["duplicate_of"] = ["A duplicate must reference a finalized materialized batch."]
            elif target is not None and target.source_artifact_id != self.source_artifact_id:
                errors["duplicate_of"] = ["A duplicate must use the same source artifact."]
            elif target is not None and target.account_id != self.account_id:
                errors["duplicate_of"] = ["A duplicate must use the same account."]

        if errors:
            raise ValidationError(errors)


class RawRecord(models.Model):
    class RowClass(models.TextChoices):
        METADATA = "metadata", "Metadata"
        MOVEMENT_CANDIDATE = "movement_candidate", "Movement candidate"
        HEADER = "header", "Header"
        BLANK = "blank", "Blank"
        AUXILIARY = "auxiliary", "Auxiliary"

    class ParseOutcome(models.TextChoices):
        PARSED = "PARSED", "Parsed"
        IGNORED = "IGNORED", "Ignored"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="raw_records")
    row_number = models.PositiveIntegerField()
    raw_cells = models.JSONField()
    row_class = models.CharField(max_length=32, choices=RowClass.choices)
    parse_outcome = models.CharField(max_length=8, choices=ParseOutcome.choices)
    parser_codes = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["import_batch", "row_number"],
                name="one_raw_record_per_batch_row",
            ),
            models.CheckConstraint(check=Q(row_number__gt=0), name="raw_record_positive_row"),
            models.CheckConstraint(
                check=Q(parse_outcome__in=["PARSED", "IGNORED", "REJECTED"]),
                name="raw_record_outcome_known",
            ),
        ]


class Movement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.OneToOneField(RawRecord, on_delete=models.PROTECT, related_name="movement")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="movements")
    occurrence_date = models.DateField()
    signed_amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3)
    description = models.TextField(null=True, blank=True)
    source_reference = models.TextField(null=True, blank=True)
    running_balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    amount_source_column = models.CharField(max_length=1)

    class Meta:
        constraints = [
            models.CheckConstraint(check=~Q(signed_amount=0), name="movement_signed_amount_nonzero"),
            models.CheckConstraint(check=Q(currency__regex=r"^[A-Z]{3}$"), name="movement_currency_iso_like"),
            models.CheckConstraint(check=Q(amount_source_column__in=["E", "F"]), name="movement_amount_column_known"),
        ]
        indexes = [models.Index(fields=["account", "occurrence_date"], name="movement_account_date_idx")]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        for field_name in ("signed_amount", "running_balance"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages
        if self.raw_record_id:
            raw_record = self.raw_record
            if raw_record.parse_outcome != RawRecord.ParseOutcome.PARSED:
                errors["raw_record"] = ["Only parsed raw records may have movements."]
            elif raw_record.import_batch.account_id != self.account_id:
                errors["account"] = ["Movement account must match its import batch."]
            elif self.currency != raw_record.import_batch.account.currency:
                errors["currency"] = ["Movement currency must match the trusted account currency."]
        if errors:
            raise ValidationError(errors)
