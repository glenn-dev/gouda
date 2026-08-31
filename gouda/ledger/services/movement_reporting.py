"""Read-only reporting over accepted canonical Movements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ..models import Account, Movement


class MovementReportingServiceError(ValueError):
    """A deterministic reporting-boundary failure with a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MovementSourceTrace:
    """Safe identifiers and route metadata for a Movement's source chain."""

    raw_record_id: UUID
    import_batch_id: UUID
    source_artifact_id: UUID
    source_kind: str
    source_variant: str | None
    parser_version: str
    import_status: str
    reconciliation_status: str | None


@dataclass(frozen=True)
class MovementReportItem:
    """Canonical reporting fields without source-native evidence payloads."""

    movement_id: UUID
    account_id: UUID
    occurrence_date: date
    signed_amount: Decimal
    currency: str
    description: str | None
    source_trace: MovementSourceTrace


@dataclass(frozen=True)
class MovementReport:
    """Canonical Movements for one Account and inclusive occurrence-date range."""

    account_id: UUID
    start_date: date
    end_date: date
    movements: tuple[MovementReportItem, ...]

    @property
    def movement_count(self) -> int:
        return len(self.movements)

    @property
    def net_signed_amount(self) -> Decimal:
        return sum(
            (movement.signed_amount for movement in self.movements),
            start=Decimal("0.00"),
        )


def report_canonical_movements(
    *,
    account: Account,
    start_date: date,
    end_date: date,
) -> MovementReport:
    """Return accepted Movements ordered by occurrence date and Movement UUID.

    ``Movement.occurrence_date`` is the existing canonical reporting date.
    FinancialObservation state is deliberately not consulted: observations are
    evidence, while every persisted Movement is accepted canonical truth under
    the current repository invariants.
    """

    account_id = _validated_account_id(account)
    start_date = _required_date(start_date, "start_date_invalid")
    end_date = _required_date(end_date, "end_date_invalid")
    if start_date > end_date:
        raise MovementReportingServiceError("date_range_invalid")

    if not Account.objects.filter(pk=account_id).exists():
        raise MovementReportingServiceError("account_not_found")

    rows = (
        Movement.objects.filter(
            account_id=account_id,
            occurrence_date__gte=start_date,
            occurrence_date__lte=end_date,
        )
        .select_related("raw_record__import_batch__source_artifact")
        .order_by("occurrence_date", "pk")
    )
    movements = tuple(_report_item(movement) for movement in rows)
    return MovementReport(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        movements=movements,
    )


def _validated_account_id(account: object) -> UUID:
    if not isinstance(account, Account) or account.pk is None or account._state.adding:
        raise MovementReportingServiceError("account_not_persisted")
    return account.pk


def _required_date(value: object, code: str) -> date:
    if type(value) is not date or isinstance(value, datetime):
        raise MovementReportingServiceError(code)
    return value


def _report_item(movement: Movement) -> MovementReportItem:
    raw_record = movement.raw_record
    batch = raw_record.import_batch
    return MovementReportItem(
        movement_id=movement.pk,
        account_id=movement.account_id,
        occurrence_date=movement.occurrence_date,
        signed_amount=movement.signed_amount,
        currency=movement.currency,
        description=movement.description,
        source_trace=MovementSourceTrace(
            raw_record_id=raw_record.pk,
            import_batch_id=batch.pk,
            source_artifact_id=batch.source_artifact_id,
            source_kind=batch.source_kind,
            source_variant=batch.source_variant,
            parser_version=batch.parser_version,
            import_status=batch.status,
            reconciliation_status=batch.reconciliation_status,
        ),
    )
