"""Immutable non-sensitive result types for the BCI Historical parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class BciParserStatus(str, Enum):
    RECOGNIZED = "RECOGNIZED"
    FATAL = "FATAL"


class BciRowOutcome(str, Enum):
    PARSED = "PARSED"
    IGNORED = "IGNORED"
    REJECTED = "REJECTED"


class BciReconciliationStatus(str, Enum):
    RECONCILED = "RECONCILED"
    NOT_RECONCILED = "NOT_RECONCILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BciCheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, repr=False)
class FieldProvenance:
    page_ordinal: int
    line_ordinals: tuple[int, ...]
    token_ordinals: tuple[int, ...]
    bbox: object = field(repr=False)
    role: str = "field"
    band_relation: str = "inside"
    page_width: Decimal = Decimal("612.00")
    page_height: Decimal = Decimal("792.00")
    normalized_bbox: tuple[Decimal, Decimal, Decimal, Decimal] = (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_ordinals", tuple(self.line_ordinals))
        object.__setattr__(self, "token_ordinals", tuple(self.token_ordinals))

    def __repr__(self) -> str:
        return f"FieldProvenance(page_ordinal={self.page_ordinal}, role={self.role!r})"


@dataclass(frozen=True, repr=False)
class BciHistoricalStatementMetadata:
    statement_id: str
    period_start: date
    period_end: date
    currency: str
    source_account_id: str = field(repr=False)
    opening_balance: Decimal | None = field(repr=False)
    printed_total_debits: Decimal | None = field(repr=False)
    printed_total_credits: Decimal | None = field(repr=False)
    closing_balance: Decimal | None = field(repr=False)
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __repr__(self) -> str:
        return "BciHistoricalStatementMetadata(period_present=True, currency=<redacted>)"


@dataclass(frozen=True, repr=False)
class BciHistoricalSourceRecord:
    outcome: BciRowOutcome
    reason_code: str
    page_ordinal: int
    source_row_ordinal: int
    line_ordinals: tuple[int, ...]
    token_ordinals: tuple[int, ...]
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)
    source_date_text: str | None = field(default=None, repr=False)
    accounting_date: date | None = field(default=None, repr=False)
    transaction_date: date | None = field(default=None, repr=False)
    branch: str | None = field(default=None, repr=False)
    description: str | None = field(default=None, repr=False)
    reference: str | None = field(default=None, repr=False)
    debit: Decimal | None = field(default=None, repr=False)
    credit: Decimal | None = field(default=None, repr=False)
    signed_amount: Decimal | None = field(default=None, repr=False)
    running_balance: Decimal | None = field(default=None, repr=False)
    currency: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_ordinals", tuple(self.line_ordinals))
        object.__setattr__(self, "token_ordinals", tuple(self.token_ordinals))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __repr__(self) -> str:
        return f"BciHistoricalSourceRecord(outcome={self.outcome.value!r}, page_ordinal={self.page_ordinal}, source_row_ordinal={self.source_row_ordinal}, reason_code={self.reason_code!r})"


@dataclass(frozen=True, repr=False)
class BciHistoricalReconciliationCheck:
    name: str
    status: BciCheckStatus
    difference: Decimal | None = field(default=None, repr=False)
    reason_code: str = ""
    operands: Mapping[str, Decimal] = field(default_factory=dict, repr=False)
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operands", MappingProxyType(dict(self.operands)))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True, repr=False)
class BciHistoricalReconciliation:
    status: BciReconciliationStatus
    checks: Mapping[str, BciHistoricalReconciliationCheck]
    operands: Mapping[str, Decimal] = field(default_factory=dict, repr=False)
    missing_operands: tuple[str, ...] = ()
    difference: Decimal | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))
        object.__setattr__(self, "operands", MappingProxyType(dict(self.operands)))
        object.__setattr__(self, "missing_operands", tuple(self.missing_operands))

    def __repr__(self) -> str:
        return f"BciHistoricalReconciliation(status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class BciHistoricalParseResult:
    status: BciParserStatus
    provider: str
    product: str
    source_variant: str | None
    parser_version: str
    gir_version: str
    extraction_profile_version: str
    metadata: BciHistoricalStatementMetadata | None
    records: tuple[BciHistoricalSourceRecord, ...]
    reconciliation: BciHistoricalReconciliation
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def parsed_records(self) -> tuple[BciHistoricalSourceRecord, ...]:
        return tuple(record for record in self.records if record.outcome is BciRowOutcome.PARSED)

    @property
    def rejected_records(self) -> tuple[BciHistoricalSourceRecord, ...]:
        return tuple(record for record in self.records if record.outcome is BciRowOutcome.REJECTED)

    @property
    def parsed_count(self) -> int:
        return sum(record.outcome is BciRowOutcome.PARSED for record in self.records)

    @property
    def ignored_count(self) -> int:
        return sum(record.outcome is BciRowOutcome.IGNORED for record in self.records)

    @property
    def rejected_count(self) -> int:
        return sum(record.outcome is BciRowOutcome.REJECTED for record in self.records)

    def __repr__(self) -> str:
        return f"BciHistoricalParseResult(status={self.status.value!r}, parsed={self.parsed_count}, ignored={self.ignored_count}, rejected={self.rejected_count})"
