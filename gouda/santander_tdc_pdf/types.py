"""Immutable, parser-only result types for Santander TDC PDF v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class RowOutcome(str, Enum):
    PARSED = "PARSED"
    IGNORED = "IGNORED"
    REJECTED = "REJECTED"


class ParserStatus(str, Enum):
    RECOGNIZED = "RECOGNIZED"
    FATAL = "FATAL"


class ReconciliationStatus(str, Enum):
    RECONCILED = "RECONCILED"
    NOT_RECONCILED = "NOT_RECONCILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SectionState(str, Enum):
    PREAMBLE = "preamble"
    STATEMENT_SUMMARY = "statement_summary"
    BILLED_DOMESTIC = "billed_domestic"
    BILLED_INTERNATIONAL = "billed_international"
    BILLED_INSTALLMENT = "billed_installment"
    BILLED_OTHER = "billed_other"
    PAYMENTS_CREDITS = "payments_credits"
    FINANCIAL_CHARGES = "financial_charges"
    UNBILLED = "unbilled"
    FOOTER_LEGAL = "footer_legal"
    END = "end"


class FinancialCategory(str, Enum):
    PURCHASE_CHARGE = "purchase_charge"
    PAYMENT = "payment"
    CREDIT_REFUND = "credit_refund"
    INTEREST = "interest"
    COMMISSION = "commission"
    TAX = "tax"
    INSURANCE = "insurance"
    CASH_ADVANCE = "cash_advance"


@dataclass(frozen=True, repr=False)
class AdditionalPageSpan:
    page_ordinal: int
    line_ordinals: tuple[int, ...]
    token_ordinals: tuple[int, ...]
    bbox: object = field(repr=False)
    page_width: Decimal | None = None
    page_height: Decimal | None = None
    normalized_bbox: tuple[Decimal, Decimal, Decimal, Decimal] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_ordinals", tuple(self.line_ordinals))
        object.__setattr__(self, "token_ordinals", tuple(self.token_ordinals))


@dataclass(frozen=True, repr=False)
class FieldProvenance:
    page_ordinal: int
    line_ordinals: tuple[int, ...]
    token_ordinals: tuple[int, ...]
    bbox: object = field(repr=False)
    role: str
    band_relation: str = "inside"
    additional_page_spans: tuple[AdditionalPageSpan, ...] = ()
    page_width: Decimal | None = None
    page_height: Decimal | None = None
    normalized_bbox: tuple[Decimal, Decimal, Decimal, Decimal] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_ordinals", tuple(self.line_ordinals))
        object.__setattr__(self, "token_ordinals", tuple(self.token_ordinals))
        object.__setattr__(self, "additional_page_spans", tuple(self.additional_page_spans))

    def __repr__(self) -> str:
        return f"FieldProvenance(page_ordinal={self.page_ordinal}, role={self.role!r})"


@dataclass(frozen=True, repr=False)
class StatementMetadata:
    statement_period_start: date
    statement_period_end: date
    billing_cutoff_date: date
    payment_due_date: date
    card_product_context: str
    card_last_four: str = field(repr=False)
    statement_currency: str | None = field(default=None, repr=False)
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.card_last_four, str)
            or len(self.card_last_four) != 4
            or any(character < "0" or character > "9" for character in self.card_last_four)
        ):
            raise ValueError("card_last_four must contain exactly four decimal digits")
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __repr__(self) -> str:
        return "StatementMetadata(period_present=True, cutoff_present=True, due_present=True)"


@dataclass(frozen=True, repr=False)
class SourceRecord:
    outcome: RowOutcome
    reason_code: str
    page_ordinal: int
    section: SectionState
    row_group_ordinal: int
    line_ordinals: tuple[int, ...]
    token_ordinals: tuple[int, ...]
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)
    transaction_date: date | None = field(default=None, repr=False)
    description_detail: str | None = field(default=None, repr=False)
    location: str | None = field(default=None, repr=False)
    reference_authorization: str | None = field(default=None, repr=False)
    billed_currency: str | None = field(default=None, repr=False)
    billed_amount: Decimal | None = field(default=None, repr=False)
    section_category: FinancialCategory | None = field(default=None, repr=False)
    debt_effect: Decimal | None = field(default=None, repr=False)
    installment_number: int | None = field(default=None, repr=False)
    installment_amount: Decimal | None = field(default=None, repr=False)
    header_profile: str | None = None
    original_amount: Decimal | None = field(default=None, repr=False)
    original_currency: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (self.original_amount is None) != (self.original_currency is None):
            raise ValueError("original amount and currency must be present together")
        object.__setattr__(self, "line_ordinals", tuple(self.line_ordinals))
        object.__setattr__(self, "token_ordinals", tuple(self.token_ordinals))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __repr__(self) -> str:
        return f"SourceRecord(outcome={self.outcome.value!r}, page_ordinal={self.page_ordinal}, row_group_ordinal={self.row_group_ordinal}, reason_code={self.reason_code!r})"


@dataclass(frozen=True, repr=False)
class ReconciliationEvidence:
    status: ReconciliationStatus
    operands: Mapping[str, Decimal] = field(default_factory=dict, repr=False)
    difference: Decimal | None = field(default=None, repr=False)
    missing_operands: tuple[str, ...] = ()
    fields: Mapping[str, FieldProvenance] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operands", MappingProxyType(dict(self.operands)))
        object.__setattr__(self, "missing_operands", tuple(self.missing_operands))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def __repr__(self) -> str:
        return f"ReconciliationEvidence(status={self.status.value!r})"


@dataclass(frozen=True, repr=False)
class TdcPdfParserResult:
    status: ParserStatus
    provider: str
    product: str
    source_variant: str
    parser_version: str
    metadata: StatementMetadata | None
    records: tuple[SourceRecord, ...]
    reconciliation: ReconciliationEvidence
    gir_version: str = ""
    extraction_profile_version: str = ""
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def parsed_records(self) -> tuple[SourceRecord, ...]:
        return tuple(record for record in self.records if record.outcome is RowOutcome.PARSED)

    @property
    def parsed_count(self) -> int:
        return sum(record.outcome is RowOutcome.PARSED for record in self.records)

    @property
    def ignored_count(self) -> int:
        return sum(record.outcome is RowOutcome.IGNORED for record in self.records)

    @property
    def rejected_count(self) -> int:
        return sum(record.outcome is RowOutcome.REJECTED for record in self.records)

    def __repr__(self) -> str:
        return f"TdcPdfParserResult(status={self.status.value!r}, parsed={self.parsed_count}, ignored={self.ignored_count}, rejected={self.rejected_count})"
