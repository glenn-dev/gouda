"""Deterministic, synthetic-only local demo ledger data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from typing import Any
from uuid import UUID, uuid5

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.db.models.deletion import ProtectedError

from .models import Account, ImportBatch, Movement, RawRecord, SourceArtifact


DEMO_VERSION = "gouda_demo_v1"
DEMO_NAMESPACE = UUID("7ad0412a-45c1-4f5d-a9bb-51ced4175274")
DEMO_PERIOD_START = date(2026, 1, 1)
DEMO_PERIOD_END = date(2026, 4, 30)
_COMPLETED_AT = datetime(2026, 5, 1, tzinfo=timezone.utc)


class DemoDataError(RuntimeError):
    """Safe deterministic failure while managing the bounded demo graph."""


@dataclass(frozen=True)
class DemoMovementSpec:
    key: str
    account_key: str
    occurrence_date: date
    signed_amount: Decimal
    description: str


@dataclass(frozen=True)
class DemoAccountSpec:
    key: str
    display_name: str
    kind: str
    economic_orientation: str
    currency: str
    source_kind: str
    record_kind: str
    artifact_filename: str
    artifact_content: bytes


@dataclass(frozen=True)
class DemoChangeResult:
    accounts: int
    movements: int


ACCOUNT_SPECS = (
    DemoAccountSpec(
        key="current",
        display_name="Synthetic Everyday Account",
        kind=Account.Kind.CURRENT,
        economic_orientation=Account.EconomicOrientation.ASSET,
        currency="CLP",
        source_kind=ImportBatch.SourceKind.DEMO_SYNTHETIC,
        record_kind=RawRecord.RecordKind.DEMO_SYNTHETIC_RECORD,
        artifact_filename="gouda-demo-synthetic-current-v1.txt",
        artifact_content=b"GOUDA SYNTHETIC DEMO CURRENT ACCOUNT V1\n",
    ),
    DemoAccountSpec(
        key="card",
        display_name="Synthetic Household Card",
        kind=Account.Kind.CREDIT_CARD,
        economic_orientation=Account.EconomicOrientation.LIABILITY,
        currency="CLP",
        source_kind=ImportBatch.SourceKind.DEMO_SYNTHETIC,
        record_kind=RawRecord.RecordKind.DEMO_SYNTHETIC_RECORD,
        artifact_filename="gouda-demo-synthetic-card-v1.txt",
        artifact_content=b"GOUDA SYNTHETIC DEMO CREDIT CARD V1\n",
    ),
)

MOVEMENT_SPECS = (
    DemoMovementSpec(
        "current-salary-january",
        "current",
        date(2026, 1, 5),
        Decimal("2500000.00"),
        "Synthetic salary deposit",
    ),
    DemoMovementSpec(
        "current-grocery-january",
        "current",
        date(2026, 1, 9),
        Decimal("-85430.00"),
        "Synthetic grocery purchase",
    ),
    DemoMovementSpec(
        "current-utility-february",
        "current",
        date(2026, 2, 12),
        Decimal("-49120.00"),
        "Synthetic utility bill",
    ),
    DemoMovementSpec(
        "current-salary-april",
        "current",
        date(2026, 4, 5),
        Decimal("2500000.00"),
        "Synthetic salary deposit",
    ),
    DemoMovementSpec(
        "current-restaurant-april",
        "current",
        date(2026, 4, 18),
        Decimal("-36750.00"),
        "Synthetic restaurant purchase",
    ),
    DemoMovementSpec(
        "current-refund-april",
        "current",
        date(2026, 4, 22),
        Decimal("12990.00"),
        "Synthetic merchant refund",
    ),
    DemoMovementSpec(
        "card-grocery-january",
        "card",
        date(2026, 1, 10),
        Decimal("-85430.00"),
        "Synthetic card grocery purchase",
    ),
    DemoMovementSpec(
        "card-payment-january",
        "card",
        date(2026, 1, 25),
        Decimal("120000.00"),
        "Synthetic liability balance reduction",
    ),
    DemoMovementSpec(
        "card-utility-february",
        "card",
        date(2026, 2, 13),
        Decimal("-49120.00"),
        "Synthetic card utility purchase",
    ),
    DemoMovementSpec(
        "card-restaurant-april",
        "card",
        date(2026, 4, 19),
        Decimal("-36750.00"),
        "Synthetic card restaurant purchase",
    ),
    DemoMovementSpec(
        "card-refund-april",
        "card",
        date(2026, 4, 23),
        Decimal("12990.00"),
        "Synthetic card refund",
    ),
)


def demo_uuid(entity: str, key: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"{DEMO_VERSION}:{entity}:{key}")


DEMO_ACCOUNT_IDS = frozenset(demo_uuid("account", spec.key) for spec in ACCOUNT_SPECS)
DEMO_ARTIFACT_IDS = frozenset(demo_uuid("artifact", spec.key) for spec in ACCOUNT_SPECS)
DEMO_BATCH_IDS = frozenset(demo_uuid("batch", spec.key) for spec in ACCOUNT_SPECS)
DEMO_RAW_RECORD_IDS = frozenset(
    demo_uuid("raw-record", spec.key) for spec in MOVEMENT_SPECS
)
DEMO_MOVEMENT_IDS = frozenset(demo_uuid("movement", spec.key) for spec in MOVEMENT_SPECS)


@transaction.atomic
def seed_demo_data() -> DemoChangeResult:
    """Create the fixed synthetic demo graph without invoking import routes."""

    accounts: dict[str, Account] = {}
    batches: dict[str, ImportBatch] = {}
    movements_by_account = {
        account_spec.key: tuple(
            spec for spec in MOVEMENT_SPECS if spec.account_key == account_spec.key
        )
        for account_spec in ACCOUNT_SPECS
    }

    try:
        for spec in ACCOUNT_SPECS:
            account, _ = _get_or_create_exact(
                Account,
                demo_uuid("account", spec.key),
                {
                    "display_name": spec.display_name,
                    "kind": spec.kind,
                    "economic_orientation": spec.economic_orientation,
                    "currency": spec.currency,
                },
            )
            accounts[spec.key] = account

            artifact, _ = _get_or_create_exact(
                SourceArtifact,
                demo_uuid("artifact", spec.key),
                {
                    "original_filename": spec.artifact_filename,
                    "content_digest": hashlib.sha256(spec.artifact_content).hexdigest(),
                    "content": spec.artifact_content,
                },
            )

            account_movements = movements_by_account[spec.key]
            batch, _ = _get_or_create_exact(
                ImportBatch,
                demo_uuid("batch", spec.key),
                {
                    "source_artifact": artifact,
                    "account": account,
                    "source_kind": spec.source_kind,
                    "parser_version": DEMO_VERSION,
                    "source_variant": DEMO_VERSION,
                    "status": ImportBatch.Status.ACCEPTED,
                    "completed_at": _COMPLETED_AT,
                    "period_start": DEMO_PERIOD_START,
                    "period_end": DEMO_PERIOD_END,
                    "parsed_count": len(account_movements),
                    "ignored_count": 0,
                    "rejected_count": 0,
                    "reconciliation_status": ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
                },
            )
            batches[spec.key] = batch

        for account_spec in ACCOUNT_SPECS:
            for ordinal, spec in enumerate(
                movements_by_account[account_spec.key], start=1
            ):
                raw_defaults: dict[str, Any] = {
                    "import_batch": batches[spec.account_key],
                    "record_kind": account_spec.record_kind,
                    "record_ordinal": ordinal,
                    "parse_outcome": RawRecord.ParseOutcome.PARSED,
                    "parser_codes": ["synthetic_demo_record"],
                }
                raw_record, _ = _get_or_create_exact(
                    RawRecord,
                    demo_uuid("raw-record", spec.key),
                    raw_defaults,
                )
                _get_or_create_exact(
                    Movement,
                    demo_uuid("movement", spec.key),
                    {
                        "raw_record": raw_record,
                        "account": accounts[spec.account_key],
                        "occurrence_date": spec.occurrence_date,
                        "signed_amount": spec.signed_amount,
                        "currency": accounts[spec.account_key].currency,
                        "description": spec.description,
                        "source_reference": None,
                        "running_balance": None,
                    },
                )
    except (IntegrityError, ValidationError) as error:
        raise DemoDataError("demo_seed_constraint_failure") from error

    return DemoChangeResult(
        accounts=Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).count(),
        movements=Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS).count(),
    )


@transaction.atomic
def clear_demo_data() -> DemoChangeResult:
    """Delete only objects carrying the fixed demo UUID namespace markers."""

    account_count = Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).count()
    movement_count = Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS).count()
    try:
        Movement.objects.filter(pk__in=DEMO_MOVEMENT_IDS).delete()
        RawRecord.objects.filter(pk__in=DEMO_RAW_RECORD_IDS).delete()
        ImportBatch.objects.filter(pk__in=DEMO_BATCH_IDS).delete()
        SourceArtifact.objects.filter(pk__in=DEMO_ARTIFACT_IDS).delete()
        Account.objects.filter(pk__in=DEMO_ACCOUNT_IDS).delete()
    except ProtectedError as error:
        raise DemoDataError("demo_cleanup_blocked_by_non_demo_data") from error

    return DemoChangeResult(accounts=account_count, movements=movement_count)


def _get_or_create_exact(
    model: type[Model],
    object_id: UUID,
    expected: dict[str, Any],
) -> tuple[Model, bool]:
    instance = model.objects.filter(pk=object_id).first()
    if instance is None:
        instance = model(pk=object_id, **expected)
        instance.full_clean()
        instance.save(force_insert=True)
        return instance, True

    for field_name, expected_value in expected.items():
        actual_value = getattr(instance, field_name)
        if isinstance(expected_value, Model):
            matches = getattr(instance, f"{field_name}_id") == expected_value.pk
        elif isinstance(expected_value, bytes):
            matches = bytes(actual_value) == expected_value
        else:
            matches = actual_value == expected_value
        if not matches:
            raise DemoDataError(
                f"demo_identity_conflict:{model._meta.label_lower}:{object_id}"
            )
    return instance, False
