"""Fail-closed BCI Current Cartola legacy-XLS v0.1 source parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
import re
from struct import error as StructError, unpack_from
from typing import BinaryIO, Iterable, Mapping
import unicodedata

import xlrd
from xlrd.biffh import XL_EOF, XL_FORMULA_OPCODES

from gouda.ledger.validation import validate_exact_money

from .types import ParseResult, ParserStatus, RowOutcome, SourceCell, SourceRecord


SOURCE_VARIANT = "bci_current_cartola_xls"
CONTRACT_VERSION = "bci_current_cartola_v0.1"
PARSER_VERSION = CONTRACT_VERSION

_CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_MONEY_RE = re.compile(r"^-?(?:\d+|\d{1,3}(?:\.\d{3})+)$")
_COLUMNS = tuple("ABCDE")
_TITLE = "movimientos de su cuenta"
_METADATA = (
    "saldo disponible",
    "saldo contable",
    "retenciones",
    "sobregiro disponible",
    "sobregiro utilizado",
    "linea de emergencia",
)
_HEADERS = ("fecha", "descripcion", "serie", "monto $", "saldo contable $")
_SUPPORTED_TITLE_MERGE = "A1:E1"
_XL_CELL_TYPES = {
    xlrd.XL_CELL_EMPTY: "empty",
    xlrd.XL_CELL_TEXT: "text",
    xlrd.XL_CELL_NUMBER: "number",
    xlrd.XL_CELL_DATE: "date",
    xlrd.XL_CELL_BOOLEAN: "boolean",
    xlrd.XL_CELL_ERROR: "error",
    xlrd.XL_CELL_BLANK: "blank",
}


class BciCurrentCartolaParserError(Exception):
    """Expected safe parser failure with a stable sanitized code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class MalformedWorkbookError(BciCurrentCartolaParserError):
    pass


class UnsupportedWorkbookError(BciCurrentCartolaParserError):
    pass


class AmbiguousWorksheetError(BciCurrentCartolaParserError):
    pass


@dataclass(frozen=True)
class _Sheet:
    alias: str
    name: str
    ordinal: int
    visible: bool
    rows: Mapping[int, Mapping[str, SourceCell]]
    populated_rows: tuple[int, ...]
    populated_columns: tuple[int, ...]
    actual_max_row: int
    actual_max_column: int
    physical_nrows: int
    physical_ncols: int
    merged_ranges: tuple[str, ...]


def parse_bci_current_cartola_xls(
    source: Path | str | bytes | BinaryIO,
    *,
    artifact_identity: str | None = None,
) -> ParseResult:
    """Parse one legacy XLS without converting or rewriting the source."""

    try:
        data = _read_source(source)
    except (OSError, TypeError, ValueError) as error:
        raise MalformedWorkbookError("xls_invalid") from error
    if not data.startswith(_CFB_SIGNATURE):
        raise MalformedWorkbookError("xls_invalid")
    try:
        sheets = _read_legacy_xls(data)
    except (xlrd.XLRDError, OSError, ValueError, IndexError, KeyError, TypeError, StructError) as error:
        raise MalformedWorkbookError("xls_invalid") from error
    return _parse_sheets(sheets, artifact_identity=artifact_identity)


def _read_source(source: Path | str | bytes | BinaryIO) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if isinstance(source, bytes):
        return source
    data = source.read()
    if not isinstance(data, bytes):
        raise TypeError("source must provide bytes")
    return data


def _read_legacy_xls(data: bytes) -> tuple[_Sheet, ...]:
    workbook = xlrd.open_workbook(
        file_contents=data,
        logfile=StringIO(),
        formatting_info=True,
        on_demand=True,
        ignore_workbook_corruption=False,
    )
    try:
        formula_coordinates = [
            _formula_coordinates(workbook, sheet_index)
            for sheet_index in range(workbook.nsheets)
        ]
        return tuple(
            _adapt_sheet(
                workbook.sheet_by_index(sheet_index),
                ordinal=sheet_index + 1,
                formula_coordinates=formula_coordinates[sheet_index],
            )
            for sheet_index in range(workbook.nsheets)
        )
    finally:
        workbook.release_resources()


def _formula_coordinates(workbook, sheet_index: int) -> frozenset[tuple[int, int]]:
    """Find BIFF formula records because xlrd exposes only their cached values."""

    memory = workbook.mem
    position = workbook._sh_abs_posn[sheet_index]
    limit = min(len(memory), workbook.base + workbook.stream_len)
    result: set[tuple[int, int]] = set()
    while position + 4 <= limit:
        code, length = unpack_from("<HH", memory, position)
        position += 4
        if position + length > limit:
            raise ValueError("truncated BIFF record")
        data = memory[position : position + length]
        position += length
        if code in XL_FORMULA_OPCODES:
            if length < 4:
                raise ValueError("truncated BIFF formula record")
            row_index, column_index = unpack_from("<HH", data, 0)
            result.add((row_index, column_index))
        if code == XL_EOF:
            return frozenset(result)
    raise ValueError("worksheet BIFF EOF missing")


def _adapt_sheet(worksheet, *, ordinal: int, formula_coordinates: frozenset[tuple[int, int]]) -> _Sheet:
    rows: dict[int, dict[str, SourceCell]] = {}
    populated_rows: set[int] = set()
    populated_columns: set[int] = set()
    actual_max_row = 0
    actual_max_column = 0
    for row_index in range(worksheet.nrows):
        row_number = row_index + 1
        adapted: dict[str, SourceCell] = {}
        for column_index in range(worksheet.ncols):
            column = _column_name(column_index + 1)
            cell = worksheet.cell(row_index, column_index)
            is_formula = (row_index, column_index) in formula_coordinates
            cell_type = "formula" if is_formula else _XL_CELL_TYPES.get(cell.ctype, "unsupported")
            source = SourceCell(
                value=cell.value,
                cell_type=cell_type,
                is_formula=is_formula,
                present=cell.ctype != xlrd.XL_CELL_EMPTY or is_formula,
            )
            adapted[column] = source
            if _is_populated(source):
                populated_rows.add(row_number)
                populated_columns.add(column_index + 1)
                actual_max_row = max(actual_max_row, row_number)
                actual_max_column = max(actual_max_column, column_index + 1)
        rows[row_number] = adapted
    return _Sheet(
        alias=f"S{ordinal}",
        name=worksheet.name,
        ordinal=ordinal,
        visible=worksheet.visibility == 0,
        rows=rows,
        populated_rows=tuple(sorted(populated_rows)),
        populated_columns=tuple(sorted(populated_columns)),
        actual_max_row=actual_max_row,
        actual_max_column=actual_max_column,
        physical_nrows=worksheet.nrows,
        physical_ncols=worksheet.ncols,
        merged_ranges=tuple(_merge_ref(*region) for region in worksheet.merged_cells),
    )


def _merge_ref(row_start: int, row_end: int, column_start: int, column_end: int) -> str:
    return (
        f"{_column_name(column_start + 1)}{row_start + 1}:"
        f"{_column_name(column_end)}{row_end}"
    )


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _parse_sheets(
    sheets: tuple[_Sheet, ...],
    *,
    artifact_identity: str | None = None,
) -> ParseResult:
    visible_matches = [sheet for sheet in sheets if sheet.visible and _matches_candidate(sheet)]
    if not visible_matches:
        raise UnsupportedWorkbookError("current_cartola_header_not_found")
    if len(visible_matches) > 1:
        raise AmbiguousWorksheetError("ambiguous_statement_worksheets")
    if len(sheets) != 1:
        raise UnsupportedWorkbookError("worksheet_count_unsupported")
    return _parse_sheet(
        visible_matches[0],
        sheet_count=len(sheets),
        artifact_identity=artifact_identity,
    )


def _matches_candidate(sheet: _Sheet) -> bool:
    if sheet.actual_max_row < 10 or sheet.actual_max_column != 5:
        return False
    if sheet.physical_ncols != 5 or sheet.merged_ranges != (_SUPPORTED_TITLE_MERGE,):
        return False
    if _normalized_text(sheet, 1, "A") != _TITLE:
        return False
    if _populated_columns(sheet, 1) != ("A",):
        return False
    for row_number, expected in enumerate(_METADATA, 2):
        if _normalized_text(sheet, row_number, "B") != expected:
            return False
        if _populated_columns(sheet, row_number) != ("B", "C"):
            return False
    if _populated_columns(sheet, 8):
        return False
    if tuple(_normalized_text(sheet, 9, column) for column in _COLUMNS) != _HEADERS:
        return False
    return _populated_columns(sheet, 9) == _COLUMNS


def _parse_sheet(
    sheet: _Sheet,
    *,
    sheet_count: int,
    artifact_identity: str | None,
) -> ParseResult:
    _validate_static_structure(sheet)
    records: list[SourceRecord] = []
    for row_number in range(1, sheet.actual_max_row + 1):
        raw = _raw_record(sheet, row_number, artifact_identity=artifact_identity)
        if row_number == 1:
            records.append(_ignored(raw, "title_row"))
        elif 2 <= row_number <= 7:
            records.append(_ignored(raw, "metadata_row"))
        elif row_number == 8:
            records.append(_ignored(raw, "separator_row"))
        elif row_number == 9:
            records.append(_ignored(raw, "header_row"))
        else:
            records.append(_parse_transaction(raw, records))
    return ParseResult(
        status=ParserStatus.RECOGNIZED,
        source_variant=SOURCE_VARIANT,
        parser_version=PARSER_VERSION,
        contract_version=CONTRACT_VERSION,
        sheet_count=sheet_count,
        sheet_alias=sheet.alias,
        worksheet_name=sheet.name,
        worksheet_ordinal=sheet.ordinal,
        actual_max_row=sheet.actual_max_row,
        actual_max_column=sheet.actual_max_column,
        records=tuple(records),
    )


def _validate_static_structure(sheet: _Sheet) -> None:
    expected_rows = tuple(range(1, 8)) + tuple(range(9, sheet.actual_max_row + 1))
    if sheet.populated_rows != expected_rows:
        raise UnsupportedWorkbookError("unexpected_empty_row")
    if sheet.populated_columns != (1, 2, 3, 4, 5):
        raise UnsupportedWorkbookError("column_geometry_unsupported")
    for row_number in range(1, 10):
        for cell in sheet.rows.get(row_number, {}).values():
            if cell.is_formula:
                raise UnsupportedWorkbookError("formula_unsupported")
            if _is_populated(cell) and cell.cell_type != "text":
                raise UnsupportedWorkbookError("cell_type_unsupported")


def _raw_record(
    sheet: _Sheet,
    row_number: int,
    *,
    artifact_identity: str | None,
) -> SourceRecord:
    raw_cells = {
        column: sheet.rows.get(row_number, {}).get(column, SourceCell())
        for column in _COLUMNS
    }
    return SourceRecord(
        raw_record_id=f"{sheet.alias}:row:{row_number}",
        sheet_alias=sheet.alias,
        worksheet_name=sheet.name,
        worksheet_ordinal=sheet.ordinal,
        row_number=row_number,
        raw_cells=raw_cells,
        outcome=RowOutcome.IGNORED,
        provenance=_provenance(
            sheet,
            row_number,
            raw_cells,
            artifact_identity=artifact_identity,
        ),
    )


def _provenance(
    sheet: _Sheet,
    row_number: int,
    cells: Mapping[str, SourceCell],
    *,
    artifact_identity: str | None,
) -> dict[str, object]:
    fields = {
        "source_date": _field_provenance(cells, row_number, "A", "Fecha"),
        "source_description": _field_provenance(cells, row_number, "B", "Descripción"),
        "source_series": _field_provenance(cells, row_number, "C", "Serie"),
        "source_signed_amount": _field_provenance(cells, row_number, "D", "Monto $"),
        "source_balance": _field_provenance(cells, row_number, "E", "Saldo Contable $"),
    }
    return {
        "artifact_identity": artifact_identity,
        "source_variant": SOURCE_VARIANT,
        "contract_version": CONTRACT_VERSION,
        "parser_version": PARSER_VERSION,
        "sheet_alias": sheet.alias,
        "worksheet_name": sheet.name,
        "worksheet_ordinal": sheet.ordinal,
        "row_number": row_number,
        "source_fields": fields,
    }


def _field_provenance(
    cells: Mapping[str, SourceCell],
    row_number: int,
    column: str,
    source_field_name: str,
) -> dict[str, object]:
    return {
        "source_field_name": source_field_name,
        "column": column,
        "coordinate": f"{column}{row_number}",
        "cell_type": cells[column].cell_type,
        "text_provenance": cells[column].cell_type == "text",
    }


def _ignored(raw: SourceRecord, reason: str) -> SourceRecord:
    return SourceRecord(
        raw_record_id=raw.raw_record_id,
        sheet_alias=raw.sheet_alias,
        worksheet_name=raw.worksheet_name,
        worksheet_ordinal=raw.worksheet_ordinal,
        row_number=raw.row_number,
        raw_cells=raw.raw_cells,
        outcome=RowOutcome.IGNORED,
        error_codes=(reason,),
        provenance=raw.provenance,
    )


def _parse_transaction(raw: SourceRecord, records: Iterable[SourceRecord]) -> SourceRecord:
    cells = raw.raw_cells
    if any(cell.is_formula for cell in cells.values()):
        return _rejected(raw, "formula_unsupported")
    if any(_is_populated(cell) and cell.cell_type != "text" for cell in cells.values()):
        return _rejected(raw, "cell_type_unsupported")

    source_date = _parse_date(cells["A"].value)
    source_signed_amount = _parse_money(cells["D"].value)
    source_balance = _parse_money(cells["E"].value)
    errors: list[str] = []
    if source_date is None:
        errors.append("date_invalid")
    if source_signed_amount is _INVALID:
        errors.append("amount_invalid")
    elif source_signed_amount is _OVERFLOW:
        errors.append("amount_precision_overflow")
    if source_balance is _INVALID:
        errors.append("balance_invalid")
    elif source_balance is _OVERFLOW:
        errors.append("balance_precision_overflow")

    prior_dates = [record.source_date for record in records if record.outcome is RowOutcome.PARSED]
    if source_date is not None and prior_dates and source_date > prior_dates[-1]:
        errors.append("source_date_order_invalid")
    if errors:
        return _rejected(raw, *errors)
    assert isinstance(source_signed_amount, Decimal)
    assert isinstance(source_balance, Decimal)
    assert source_date is not None
    return SourceRecord(
        raw_record_id=raw.raw_record_id,
        sheet_alias=raw.sheet_alias,
        worksheet_name=raw.worksheet_name,
        worksheet_ordinal=raw.worksheet_ordinal,
        row_number=raw.row_number,
        raw_cells=raw.raw_cells,
        outcome=RowOutcome.PARSED,
        source_date=source_date,
        source_description=_clean_optional(cells["B"].value),
        source_series=_clean_optional(cells["C"].value),
        source_signed_amount=source_signed_amount,
        source_balance=source_balance,
        provenance=raw.provenance,
    )


def _rejected(raw: SourceRecord, *errors: str) -> SourceRecord:
    return SourceRecord(
        raw_record_id=raw.raw_record_id,
        sheet_alias=raw.sheet_alias,
        worksheet_name=raw.worksheet_name,
        worksheet_ordinal=raw.worksheet_ordinal,
        row_number=raw.row_number,
        raw_cells=raw.raw_cells,
        outcome=RowOutcome.REJECTED,
        error_codes=tuple(errors),
        provenance=raw.provenance,
    )


def _parse_date(value: object | None) -> date | None:
    text = _clean_optional(value)
    if text is None or _DATE_RE.fullmatch(text) is None:
        return None
    try:
        return datetime.strptime(text, "%d-%m-%Y").date()
    except ValueError:
        return None


_INVALID = object()
_OVERFLOW = object()


def _parse_money(value: object | None):
    text = _clean_optional(value)
    if text is None or _MONEY_RE.fullmatch(text) is None:
        return _INVALID
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    integer = digits.replace(".", "")
    try:
        parsed = Decimal(f"{'-' if negative else ''}{integer}.00")
    except InvalidOperation:
        return _INVALID
    try:
        validate_exact_money(parsed)
    except Exception:
        return _OVERFLOW
    return parsed


def _normalized_text(sheet: _Sheet, row_number: int, column: str) -> str:
    cell = sheet.rows.get(row_number, {}).get(column)
    if cell is None or cell.is_formula or cell.cell_type != "text" or cell.value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(cell.value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().casefold()


def _clean_optional(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _is_populated(cell: SourceCell) -> bool:
    return cell.is_formula or (
        cell.present
        and cell.cell_type not in ("empty", "blank")
        and cell.value is not None
        and str(cell.value) != ""
    )


def _populated_columns(sheet: _Sheet, row_number: int) -> tuple[str, ...]:
    return tuple(
        column
        for column, cell in sheet.rows.get(row_number, {}).items()
        if _is_populated(cell)
    )
