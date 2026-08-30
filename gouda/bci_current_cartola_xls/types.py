"""Source-native immutable result types for BCI Current Cartola."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ParserStatus(str, Enum):
    RECOGNIZED = "RECOGNIZED"
    FATAL = "FATAL"


class RowOutcome(str, Enum):
    PARSED = "PARSED"
    IGNORED = "IGNORED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, repr=False)
class SourceCell:
    """A workbook-local cell whose private value is omitted from repr output."""

    value: object | None = field(default=None, repr=False)
    cell_type: str | None = None
    is_formula: bool = False
    present: bool = False

    def __repr__(self) -> str:
        return (
            f"SourceCell(cell_type={self.cell_type!r}, is_formula={self.is_formula}, "
            f"present={self.present})"
        )


@dataclass(frozen=True, repr=False)
class SourceRecord:
    """One immutable source-row interpretation."""

    raw_record_id: str
    sheet_alias: str
    worksheet_name: str = field(repr=False)
    worksheet_ordinal: int
    row_number: int
    raw_cells: Mapping[str, SourceCell] = field(repr=False)
    outcome: RowOutcome
    error_codes: tuple[str, ...] = ()
    source_date: date | None = field(default=None, repr=False)
    source_description: str | None = field(default=None, repr=False)
    source_series: str | None = field(default=None, repr=False)
    source_signed_amount: Decimal | None = field(default=None, repr=False)
    source_balance: Decimal | None = field(default=None, repr=False)
    provenance: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_cells", MappingProxyType(dict(self.raw_cells)))
        object.__setattr__(self, "error_codes", tuple(self.error_codes))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    def __repr__(self) -> str:
        return (
            f"SourceRecord(raw_record_id={self.raw_record_id!r}, row_number={self.row_number}, "
            f"outcome={self.outcome.value!r})"
        )


@dataclass(frozen=True, repr=False)
class ParseResult:
    status: ParserStatus
    source_variant: str | None
    parser_version: str
    contract_version: str
    sheet_count: int
    sheet_alias: str | None
    worksheet_name: str | None = field(default=None, repr=False)
    worksheet_ordinal: int | None = None
    actual_max_row: int | None = None
    actual_max_column: int | None = None
    records: tuple[SourceRecord, ...] = ()
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
        return (
            f"ParseResult(status={self.status.value!r}, source_variant={self.source_variant!r}, "
            f"parsed={self.parsed_count}, ignored={self.ignored_count}, rejected={self.rejected_count})"
        )
