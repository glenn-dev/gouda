"""Minimal relational model for the Gouda import/persistence boundary."""

from __future__ import annotations

import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from gouda.santander_tdc_pdf.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    SantanderTdcProvenanceError,
    validate_field_provenance_payload,
    validate_positive_ordinal_list,
)
from gouda.bci_historical_pdf.provenance import (
    BciHistoricalProvenanceError,
    PROVENANCE_SCHEMA_VERSION as BCI_PROVENANCE_SCHEMA_VERSION,
    validate_field_provenance_payload as validate_bci_field_provenance_payload,
    validate_positive_ordinal_list as validate_bci_positive_ordinal_list,
)

from .validation import validate_exact_money


class Account(models.Model):
    class Kind(models.TextChoices):
        CURRENT = "CURRENT", "Current account"
        CREDIT_CARD = "CREDIT_CARD", "Credit card"

    class EconomicOrientation(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    economic_orientation = models.CharField(
        max_length=9,
        choices=EconomicOrientation.choices,
    )
    currency = models.CharField(max_length=3)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(currency__regex=r"^[A-Z]{3}$"),
                name="account_currency_iso_like",
            ),
            models.CheckConstraint(
                check=(
                    Q(kind="CURRENT", economic_orientation="ASSET")
                    | Q(kind="CREDIT_CARD", economic_orientation="LIABILITY")
                ),
                name="account_kind_orientation_known",
            ),
        ]

    def __str__(self) -> str:
        return f"Account {self.pk}"


class SantanderTdcAccountBinding(models.Model):
    """Trusted Santander card suffix used only to verify TDC source binding."""

    account = models.OneToOneField(
        Account,
        on_delete=models.PROTECT,
        related_name="santander_tdc_binding",
    )
    card_last_four = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(card_last_four__regex=r"^[0-9]{4}$"),
                name="tdc_binding_card_last_four_shape",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.account_id and (
            self.account.kind != Account.Kind.CREDIT_CARD
            or self.account.economic_orientation != Account.EconomicOrientation.LIABILITY
        ):
            raise ValidationError(
                {"account": ["Santander TDC binding requires a liability credit-card account."]}
            )

    def __str__(self) -> str:
        return f"Santander TDC binding {self.pk}"


class SourceArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    class SourceKind(models.TextChoices):
        SANTANDER_CURRENT_ACCOUNT_XLSX = (
            "SANTANDER_CURRENT_ACCOUNT_XLSX",
            "Santander current-account XLSX",
        )
        SANTANDER_CREDIT_CARD_PDF = (
            "SANTANDER_CREDIT_CARD_PDF",
            "Santander credit-card PDF",
        )
        BCI_HISTORICAL_CURRENT_ACCOUNT_PDF = (
            "BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
            "BCI historical current-account PDF",
        )
        DEMO_SYNTHETIC = "DEMO_SYNTHETIC", "Synthetic local demo"

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
    source_kind = models.CharField(max_length=64, choices=SourceKind.choices)
    parser_version = models.CharField(max_length=64)
    source_variant = models.CharField(max_length=64, null=True, blank=True)
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
                check=Q(
                    source_kind__in=[
                        "SANTANDER_CURRENT_ACCOUNT_XLSX",
                        "SANTANDER_CREDIT_CARD_PDF",
                        "BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
                        "DEMO_SYNTHETIC",
                    ]
                ),
                name="batch_source_kind_known",
            ),
            models.CheckConstraint(
                check=(
                    Q(source_kind="SANTANDER_CURRENT_ACCOUNT_XLSX")
                    | Q(
                        source_kind="SANTANDER_CREDIT_CARD_PDF",
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                    | Q(
                        source_kind="BCI_HISTORICAL_CURRENT_ACCOUNT_PDF",
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                    | Q(
                        source_kind="DEMO_SYNTHETIC",
                        sheet_alias__isnull=True,
                        worksheet_name__isnull=True,
                        worksheet_ordinal__isnull=True,
                    )
                ),
                name="batch_tdc_sheet_fields_null",
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
            elif target is not None and target.source_kind != self.source_kind:
                errors["source_kind"] = ["A duplicate must use the canonical batch source kind."]

        if errors:
            raise ValidationError(errors)


class RawRecord(models.Model):
    class RecordKind(models.TextChoices):
        SANTANDER_XLSX_ROW = "SANTANDER_XLSX_ROW", "Santander XLSX row"
        SANTANDER_TDC_PDF_RECORD = (
            "SANTANDER_TDC_PDF_RECORD",
            "Santander TDC PDF record",
        )
        BCI_HISTORICAL_PDF_RECORD = (
            "BCI_HISTORICAL_PDF_RECORD",
            "BCI historical PDF record",
        )
        DEMO_SYNTHETIC_RECORD = "DEMO_SYNTHETIC_RECORD", "Synthetic demo record"

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
    record_kind = models.CharField(max_length=32, choices=RecordKind.choices)
    record_ordinal = models.PositiveIntegerField()
    row_number = models.PositiveIntegerField(null=True, blank=True)
    raw_cells = models.JSONField(null=True, blank=True)
    row_class = models.CharField(max_length=32, choices=RowClass.choices, null=True, blank=True)
    xlsx_amount_source_column = models.CharField(max_length=1, null=True, blank=True)
    parse_outcome = models.CharField(max_length=8, choices=ParseOutcome.choices)
    parser_codes = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["import_batch", "row_number"],
                name="one_raw_record_per_batch_row",
            ),
            models.UniqueConstraint(
                fields=["import_batch", "record_ordinal"],
                name="one_raw_record_per_batch_ordinal",
            ),
            models.CheckConstraint(check=Q(record_ordinal__gt=0), name="raw_record_positive_ordinal"),
            models.CheckConstraint(
                check=Q(row_number__isnull=True) | Q(row_number__gt=0),
                name="raw_record_positive_row",
            ),
            models.CheckConstraint(
                check=Q(
                    record_kind__in=[
                        "SANTANDER_XLSX_ROW",
                        "SANTANDER_TDC_PDF_RECORD",
                        "BCI_HISTORICAL_PDF_RECORD",
                        "DEMO_SYNTHETIC_RECORD",
                    ]
                ),
                name="raw_record_kind_known",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        row_number__isnull=False,
                        raw_cells__isnull=False,
                        row_class__isnull=False,
                    )
                    | Q(
                        record_kind="SANTANDER_TDC_PDF_RECORD",
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind="BCI_HISTORICAL_PDF_RECORD",
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind="DEMO_SYNTHETIC_RECORD",
                        row_number__isnull=True,
                        raw_cells__isnull=True,
                        row_class__isnull=True,
                        xlsx_amount_source_column__isnull=True,
                    )
                ),
                name="raw_record_kind_shape",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        parse_outcome="PARSED",
                        xlsx_amount_source_column__in=["E", "F"],
                    )
                    | Q(
                        record_kind="SANTANDER_XLSX_ROW",
                        parse_outcome__in=["IGNORED", "REJECTED"],
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind="SANTANDER_TDC_PDF_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind="BCI_HISTORICAL_PDF_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                    | Q(
                        record_kind="DEMO_SYNTHETIC_RECORD",
                        xlsx_amount_source_column__isnull=True,
                    )
                ),
                name="raw_record_xlsx_amount_shape",
            ),
            models.CheckConstraint(
                check=Q(parse_outcome__in=["PARSED", "IGNORED", "REJECTED"]),
                name="raw_record_outcome_known",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.import_batch_id:
            expected_source_kind = {
                self.RecordKind.SANTANDER_XLSX_ROW: ImportBatch.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX,
                self.RecordKind.SANTANDER_TDC_PDF_RECORD: ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF,
                self.RecordKind.BCI_HISTORICAL_PDF_RECORD: ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF,
                self.RecordKind.DEMO_SYNTHETIC_RECORD: ImportBatch.SourceKind.DEMO_SYNTHETIC,
            }.get(self.record_kind)
            if expected_source_kind and self.import_batch.source_kind != expected_source_kind:
                errors["record_kind"] = ["Raw record kind must match its import batch source kind."]
        if errors:
            raise ValidationError(errors)


class Movement(models.Model):
    """Canonical account effect and the RawRecord that originally materialized it.

    Additional evidence may support this Movement through resolved financial
    observations. ``raw_record`` remains the required originating record, not
    a claim that it is the only supporting evidence.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.OneToOneField(RawRecord, on_delete=models.PROTECT, related_name="movement")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="movements")
    occurrence_date = models.DateField()
    signed_amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3)
    description = models.TextField(null=True, blank=True)
    source_reference = models.TextField(null=True, blank=True)
    running_balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=~Q(signed_amount=0), name="movement_signed_amount_nonzero"),
            models.CheckConstraint(check=Q(currency__regex=r"^[A-Z]{3}$"), name="movement_currency_iso_like"),
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


class FinancialObservation(models.Model):
    """One claim immutable through supported service and model-save writes."""

    class State(models.TextChoices):
        UNRESOLVED = "UNRESOLVED", "Unresolved"
        RESOLVED = "RESOLVED", "Resolved"
        REJECTED = "REJECTED", "Rejected"
        CONFLICT = "CONFLICT", "Conflict"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    IMMUTABLE_FIELD_ATTNAMES = (
        "raw_record_id",
        "account_id",
        "transaction_date",
        "accounting_date",
        "signed_amount",
        "currency",
        "description",
        "source_reference",
        "interpretation_method",
        "interpretation_version",
        "idempotency_key",
        "created_at",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.ForeignKey(
        RawRecord,
        on_delete=models.PROTECT,
        related_name="financial_observations",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="financial_observations",
    )
    transaction_date = models.DateField(null=True, blank=True)
    accounting_date = models.DateField(null=True, blank=True)
    signed_amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3)
    description = models.TextField(null=True, blank=True)
    source_reference = models.TextField(null=True, blank=True)
    interpretation_method = models.CharField(max_length=64)
    interpretation_version = models.CharField(max_length=64)
    idempotency_key = models.UUIDField(unique=True)
    state = models.CharField(
        max_length=12,
        choices=State.choices,
        default=State.UNRESOLVED,
    )
    current_movement = models.ForeignKey(
        Movement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="supporting_observations",
    )
    state_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~Q(signed_amount=0),
                name="observation_signed_amount_nonzero",
            ),
            models.CheckConstraint(
                check=Q(currency__regex=r"^[A-Z]{3}$"),
                name="observation_currency_iso_like",
            ),
            models.CheckConstraint(
                check=Q(transaction_date__isnull=False) | Q(accounting_date__isnull=False),
                name="observation_financial_date_present",
            ),
            models.CheckConstraint(
                check=Q(
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
                check=~Q(interpretation_method="") & ~Q(interpretation_version=""),
                name="observation_interpreter_nonempty",
            ),
            models.CheckConstraint(
                check=(
                    Q(state__in=["RESOLVED", "CONFLICT"], current_movement__isnull=False)
                    | Q(
                        state__in=["UNRESOLVED", "REJECTED", "SUPERSEDED"],
                        current_movement__isnull=True,
                    )
                ),
                name="observation_state_movement_shape",
            ),
            models.CheckConstraint(
                check=Q(state_version__gte=0),
                name="observation_state_version_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["account", "transaction_date"],
                name="observation_account_tx_idx",
            ),
            models.Index(
                fields=["account", "accounting_date"],
                name="observation_account_acct_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        try:
            validate_exact_money(self.signed_amount, field_name="signed_amount")
        except ValidationError as exc:
            errors["signed_amount"] = exc.messages
        if self.signed_amount == 0:
            errors["signed_amount"] = ["Observation signed amount must be nonzero."]
        if self.transaction_date is None and self.accounting_date is None:
            errors["transaction_date"] = ["At least one financial date is required."]
        if self.raw_record_id:
            raw_record = self.raw_record
            if raw_record.parse_outcome != RawRecord.ParseOutcome.PARSED:
                errors["raw_record"] = ["Only parsed raw records may produce observations."]
            elif raw_record.import_batch.account_id != self.account_id:
                errors["account"] = ["Observation account must match its import batch."]
        if self.account_id and self.currency != self.account.currency:
            errors["currency"] = ["Observation currency must match the trusted account currency."]
        state_requires_movement = self.state in {self.State.RESOLVED, self.State.CONFLICT}
        if state_requires_movement != bool(self.current_movement_id):
            errors["current_movement"] = ["Observation state and current Movement are inconsistent."]
        if self.current_movement_id:
            movement = self.current_movement
            if movement.account_id != self.account_id:
                errors["current_movement"] = ["Observation and Movement accounts must match."]
            elif movement.currency != self.currency:
                errors["current_movement"] = ["Observation and Movement currencies must match."]
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding and self.pk:
            persisted = type(self).objects.filter(pk=self.pk).values(
                *self.IMMUTABLE_FIELD_ATTNAMES
            ).first()
            if persisted is not None:
                changed = [
                    field
                    for field in self.IMMUTABLE_FIELD_ATTNAMES
                    if getattr(self, field) != persisted[field]
                ]
                if changed:
                    raise ValidationError(
                        {"__all__": ["Financial observation claim fields are immutable."]},
                        code="observation_claim_immutable",
                    )
        super().save(*args, **kwargs)


class ObservationResolution(models.Model):
    """Append-only audit of one accepted observation lifecycle transition."""

    class Action(models.TextChoices):
        CONFIRM_NEW = "CONFIRM_NEW", "Confirm as new Movement"
        MATCH_EXISTING = "MATCH_EXISTING", "Match existing Movement"
        REJECT = "REJECT", "Reject"
        MARK_CONFLICT = "MARK_CONFLICT", "Mark conflict"
        REOPEN = "REOPEN", "Reopen"
        SUPERSEDE = "SUPERSEDE", "Supersede"

    class DecisionSource(models.TextChoices):
        DETERMINISTIC_POLICY = "DETERMINISTIC_POLICY", "Deterministic policy"
        HUMAN = "HUMAN", "Human"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    observation = models.ForeignKey(
        FinancialObservation,
        on_delete=models.PROTECT,
        related_name="resolutions",
    )
    sequence = models.PositiveIntegerField()
    action = models.CharField(max_length=16, choices=Action.choices)
    from_state = models.CharField(max_length=12, choices=FinancialObservation.State.choices)
    to_state = models.CharField(max_length=12, choices=FinancialObservation.State.choices)
    movement = models.ForeignKey(
        Movement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="observation_resolutions",
    )
    successor_observation = models.ForeignKey(
        FinancialObservation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseding_resolutions",
    )
    decision_source = models.CharField(max_length=24, choices=DecisionSource.choices)
    policy_name = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=64)
    reason_code = models.CharField(max_length=64)
    idempotency_key = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["observation", "sequence"],
                name="one_resolution_per_observation_sequence",
            ),
            models.CheckConstraint(
                check=Q(sequence__gt=0),
                name="resolution_sequence_positive",
            ),
            models.CheckConstraint(
                check=Q(
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
                check=Q(
                    decision_source__in=["DETERMINISTIC_POLICY", "HUMAN"]
                ),
                name="resolution_decision_source_known",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(policy_name="")
                    & ~Q(policy_version="")
                    & ~Q(reason_code="")
                ),
                name="resolution_required_text_nonempty",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        action__in=["CONFIRM_NEW", "MATCH_EXISTING"],
                        from_state="UNRESOLVED",
                        to_state="RESOLVED",
                        movement__isnull=False,
                        successor_observation__isnull=True,
                    )
                    | Q(
                        action="REJECT",
                        from_state="UNRESOLVED",
                        to_state="REJECTED",
                        movement__isnull=True,
                        successor_observation__isnull=True,
                    )
                    | Q(
                        action="MARK_CONFLICT",
                        from_state__in=["UNRESOLVED", "RESOLVED"],
                        to_state="CONFLICT",
                        movement__isnull=False,
                        successor_observation__isnull=True,
                    )
                    | Q(
                        action="REOPEN",
                        from_state="REJECTED",
                        to_state="UNRESOLVED",
                        movement__isnull=True,
                        successor_observation__isnull=True,
                    )
                    | Q(
                        action="REOPEN",
                        from_state="CONFLICT",
                        to_state="UNRESOLVED",
                        movement__isnull=False,
                        successor_observation__isnull=True,
                    )
                    | Q(
                        action="SUPERSEDE",
                        from_state__in=["UNRESOLVED", "REJECTED"],
                        to_state="SUPERSEDED",
                        movement__isnull=True,
                        successor_observation__isnull=False,
                    )
                    | Q(
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
                check=Q(successor_observation__isnull=True)
                | ~Q(successor_observation=F("observation")),
                name="resolution_successor_not_self",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.movement_id:
            if self.movement.account_id != self.observation.account_id:
                errors["movement"] = ["Resolution Movement account must match the observation."]
            elif self.movement.currency != self.observation.currency:
                errors["movement"] = ["Resolution Movement currency must match the observation."]
        if self.successor_observation_id:
            successor = self.successor_observation
            if successor.pk == self.observation_id:
                errors["successor_observation"] = ["An observation cannot supersede itself."]
            elif successor.raw_record_id != self.observation.raw_record_id:
                errors["successor_observation"] = ["A corrected interpretation must use the same raw record."]
            elif successor.account_id != self.observation.account_id:
                errors["successor_observation"] = ["Superseded observations must use the same account."]
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding and self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                {"__all__": ["Observation resolution history is append-only."]},
                code="observation_resolution_append_only",
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            {"__all__": ["Observation resolution history is append-only."]},
            code="observation_resolution_append_only",
        )


class SantanderTdcPdfBatchEvidence(models.Model):
    import_batch = models.OneToOneField(
        ImportBatch,
        on_delete=models.PROTECT,
        related_name="santander_tdc_pdf_evidence",
    )
    provenance_schema_version = models.CharField(
        max_length=64,
        choices=[(PROVENANCE_SCHEMA_VERSION, PROVENANCE_SCHEMA_VERSION)],
    )
    gir_version = models.CharField(max_length=64)
    extraction_profile_version = models.CharField(max_length=64)
    billing_cutoff_date = models.DateField()
    payment_due_date = models.DateField()
    statement_currency = models.CharField(max_length=3, null=True, blank=True)
    card_product_context = models.CharField(max_length=64)
    card_last_four = models.CharField(max_length=4)
    metadata_provenance = models.JSONField()
    reconciliation_missing_operands = models.JSONField(default=list, blank=True)
    reconciliation_provenance = models.JSONField()
    purchases_charges = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    payments_credits = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    financial_charges = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(provenance_schema_version=PROVENANCE_SCHEMA_VERSION),
                name="tdc_batch_provenance_schema_known",
            ),
            models.CheckConstraint(
                check=(~Q(gir_version="") & ~Q(extraction_profile_version="") & ~Q(card_product_context="")),
                name="tdc_batch_required_text_nonempty",
            ),
            models.CheckConstraint(
                check=Q(card_last_four__regex=r"^[0-9]{4}$"),
                name="tdc_batch_card_last_four_shape",
            ),
            models.CheckConstraint(
                check=Q(statement_currency__isnull=True) | Q(statement_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_batch_currency_iso_like",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.import_batch_id and self.import_batch.source_kind != ImportBatch.SourceKind.SANTANDER_CREDIT_CARD_PDF:
            errors["import_batch"] = ["TDC batch evidence requires a Santander credit-card PDF batch."]
        for field_name in ("purchases_charges", "payments_credits", "financial_charges"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages
        for field_name in ("metadata_provenance", "reconciliation_provenance"):
            try:
                validate_field_provenance_payload(getattr(self, field_name))
            except SantanderTdcProvenanceError as exc:
                errors[field_name] = [exc.code]
        allowed_operands = {
            "previous_balance",
            "current_billed_balance",
            "purchases_charges",
            "payments_credits",
            "financial_charges",
        }
        missing = self.reconciliation_missing_operands
        if (
            not isinstance(missing, list)
            or any(not isinstance(item, str) or item not in allowed_operands for item in missing)
            or len(set(missing)) != len(missing)
        ):
            errors["reconciliation_missing_operands"] = ["Invalid reconciliation operand list."]
        if errors:
            raise ValidationError(errors)


class SantanderTdcPdfRecordEvidence(models.Model):
    class Section(models.TextChoices):
        PREAMBLE = "preamble", "Preamble"
        STATEMENT_SUMMARY = "statement_summary", "Statement summary"
        BILLED_DOMESTIC = "billed_domestic", "Billed domestic"
        BILLED_INTERNATIONAL = "billed_international", "Billed international"
        BILLED_INSTALLMENT = "billed_installment", "Billed installment"
        BILLED_OTHER = "billed_other", "Billed other"
        PAYMENTS_CREDITS = "payments_credits", "Payments and credits"
        FINANCIAL_CHARGES = "financial_charges", "Financial charges"
        UNBILLED = "unbilled", "Unbilled"
        FOOTER_LEGAL = "footer_legal", "Footer/legal"
        END = "end", "End"

    class Category(models.TextChoices):
        PURCHASE_CHARGE = "purchase_charge", "Purchase/charge"
        PAYMENT = "payment", "Payment"
        CREDIT_REFUND = "credit_refund", "Credit/refund"
        INTEREST = "interest", "Interest"
        COMMISSION = "commission", "Commission"
        TAX = "tax", "Tax"
        INSURANCE = "insurance", "Insurance"
        CASH_ADVANCE = "cash_advance", "Cash advance"

    raw_record = models.OneToOneField(
        RawRecord,
        on_delete=models.PROTECT,
        related_name="santander_tdc_pdf_evidence",
    )
    page_ordinal = models.PositiveIntegerField()
    section = models.CharField(max_length=32, choices=Section.choices)
    row_group_ordinal = models.PositiveIntegerField()
    line_ordinals = models.JSONField()
    token_ordinals = models.JSONField()
    field_provenance = models.JSONField()
    transaction_date = models.DateField(null=True, blank=True)
    description_detail = models.TextField(null=True, blank=True)
    location = models.TextField(null=True, blank=True)
    reference_authorization = models.TextField(null=True, blank=True)
    billed_currency = models.CharField(max_length=3, null=True, blank=True)
    billed_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, null=True, blank=True)
    original_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    section_category = models.CharField(max_length=32, choices=Category.choices, null=True, blank=True)
    debt_effect = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    installment_number = models.PositiveIntegerField(null=True, blank=True)
    installment_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    header_profile = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(page_ordinal__gt=0), name="tdc_record_page_positive"),
            models.CheckConstraint(
                check=Q(
                    section__in=[
                        "preamble",
                        "statement_summary",
                        "billed_domestic",
                        "billed_international",
                        "billed_installment",
                        "billed_other",
                        "payments_credits",
                        "financial_charges",
                        "unbilled",
                        "footer_legal",
                        "end",
                    ]
                ),
                name="tdc_record_section_known",
            ),
            models.CheckConstraint(
                check=Q(section_category__isnull=True)
                | Q(
                    section_category__in=[
                        "purchase_charge",
                        "payment",
                        "credit_refund",
                        "interest",
                        "commission",
                        "tax",
                        "insurance",
                        "cash_advance",
                    ]
                ),
                name="tdc_record_category_known",
            ),
            models.CheckConstraint(
                check=Q(billed_currency__isnull=True) | Q(billed_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_record_billed_currency_iso",
            ),
            models.CheckConstraint(
                check=Q(original_currency__isnull=True) | Q(original_currency__regex=r"^[A-Z]{3}$"),
                name="tdc_record_original_currency_iso",
            ),
            models.CheckConstraint(
                check=(
                    Q(original_amount__isnull=True, original_currency__isnull=True)
                    | Q(original_amount__isnull=False, original_currency__isnull=False)
                ),
                name="tdc_record_original_pair",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.raw_record_id and self.raw_record.record_kind != RawRecord.RecordKind.SANTANDER_TDC_PDF_RECORD:
            errors["raw_record"] = ["TDC record evidence requires a Santander TDC PDF raw record."]
        for field_name in ("billed_amount", "original_amount", "debt_effect", "installment_amount"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages
        for field_name in ("line_ordinals", "token_ordinals"):
            try:
                validate_positive_ordinal_list(getattr(self, field_name))
            except SantanderTdcProvenanceError as exc:
                errors[field_name] = [exc.code]
        try:
            validate_field_provenance_payload(self.field_provenance)
        except SantanderTdcProvenanceError as exc:
            errors["field_provenance"] = [exc.code]
        if errors:
            raise ValidationError(errors)


class BciHistoricalPdfBatchEvidence(models.Model):
    """Narrow immutable source evidence for one BCI Historical statement."""

    import_batch = models.OneToOneField(
        ImportBatch,
        on_delete=models.PROTECT,
        related_name="bci_historical_pdf_evidence",
    )
    statement_id = models.CharField(max_length=64)
    source_account_id = models.CharField(max_length=64)
    statement_currency = models.CharField(max_length=3)
    gir_version = models.CharField(max_length=64)
    extraction_profile_version = models.CharField(max_length=64)
    provenance_schema_version = models.CharField(
        max_length=64,
        choices=[(BCI_PROVENANCE_SCHEMA_VERSION, BCI_PROVENANCE_SCHEMA_VERSION)],
    )
    metadata_provenance = models.JSONField()
    reconciliation_provenance = models.JSONField()
    reconciliation_checks = models.JSONField()
    reconciliation_missing_operands = models.JSONField(default=list, blank=True)
    printed_total_debits = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    printed_total_credits = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(statement_id__regex=r"^[0-9]+$"),
                name="bci_batch_statement_id_shape",
            ),
            models.CheckConstraint(
                check=Q(source_account_id__regex=r"^[0-9]+$"),
                name="bci_batch_source_account_shape",
            ),
            models.CheckConstraint(
                check=Q(statement_currency="CLP"),
                name="bci_batch_currency_clp",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(gir_version="")
                    & ~Q(extraction_profile_version="")
                ),
                name="bci_batch_versions_nonempty",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.import_batch_id and self.import_batch.source_kind != ImportBatch.SourceKind.BCI_HISTORICAL_CURRENT_ACCOUNT_PDF:
            errors["import_batch"] = ["BCI evidence requires a BCI Historical PDF batch."]
        if not isinstance(self.statement_id, str) or re.fullmatch(r"[0-9]+", self.statement_id) is None:
            errors["statement_id"] = ["Invalid BCI statement identifier."]
        if not isinstance(self.source_account_id, str) or re.fullmatch(r"[0-9]+", self.source_account_id) is None:
            errors["source_account_id"] = ["Invalid BCI source account identifier."]
        for field_name in ("printed_total_debits", "printed_total_credits"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages
        for field_name in ("metadata_provenance", "reconciliation_provenance"):
            try:
                validate_bci_field_provenance_payload(getattr(self, field_name))
            except BciHistoricalProvenanceError as exc:
                errors[field_name] = [exc.code]
        if not isinstance(self.reconciliation_checks, dict):
            errors["reconciliation_checks"] = ["Invalid reconciliation checks."]
        if not isinstance(self.reconciliation_missing_operands, list) or any(not isinstance(item, str) for item in self.reconciliation_missing_operands):
            errors["reconciliation_missing_operands"] = ["Invalid reconciliation operand list."]
        if errors:
            raise ValidationError(errors)


class BciHistoricalPdfRecordEvidence(models.Model):
    """Narrow source-native row evidence retaining exact field provenance."""

    raw_record = models.OneToOneField(
        RawRecord,
        on_delete=models.PROTECT,
        related_name="bci_historical_pdf_evidence",
    )
    page_ordinal = models.PositiveIntegerField()
    source_row_ordinal = models.PositiveIntegerField(null=True, blank=True)
    line_ordinals = models.JSONField()
    token_ordinals = models.JSONField()
    field_provenance = models.JSONField()
    source_date_text = models.TextField(null=True, blank=True)
    accounting_date = models.DateField(null=True, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    branch = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    source_reference = models.TextField(null=True, blank=True)
    debit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    signed_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    running_balance = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(page_ordinal__gt=0), name="bci_record_page_positive"),
            models.CheckConstraint(check=Q(source_row_ordinal__isnull=True) | Q(source_row_ordinal__gt=0), name="bci_record_row_positive"),
            models.CheckConstraint(check=Q(currency__isnull=True) | Q(currency="CLP"), name="bci_record_currency_clp"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}
        if self.raw_record_id and self.raw_record.record_kind != RawRecord.RecordKind.BCI_HISTORICAL_PDF_RECORD:
            errors["raw_record"] = ["BCI evidence requires a BCI Historical PDF raw record."]
        for field_name in ("debit", "credit", "signed_amount", "running_balance"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    validate_exact_money(value, field_name=field_name)
                except ValidationError as exc:
                    errors[field_name] = exc.messages
        for field_name in ("line_ordinals", "token_ordinals"):
            try:
                validate_bci_positive_ordinal_list(getattr(self, field_name))
            except BciHistoricalProvenanceError as exc:
                errors[field_name] = [exc.code]
        try:
            validate_bci_field_provenance_payload(self.field_provenance)
        except BciHistoricalProvenanceError as exc:
            errors["field_provenance"] = [exc.code]
        if errors:
            raise ValidationError(errors)
