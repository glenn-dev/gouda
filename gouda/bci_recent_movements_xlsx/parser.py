"""Fail-closed BCI Recent Movements XLSX v0.1 source parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import posixpath
import re
from typing import BinaryIO, Iterable, Mapping
from zipfile import BadZipFile, ZipFile
import unicodedata
from xml.etree import ElementTree as ET

from .types import ParseResult, ParserStatus, RowOutcome, SourceCell, SourceRecord


SOURCE_VARIANT = "bci_recent_movements_xlsx"
CONTRACT_VERSION = "bci_recent_movements_v0.1"
PARSER_VERSION = CONTRACT_VERSION

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"m": _MAIN_NS, "r": _REL_NS, "p": _PKG_REL_NS}
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MONEY_RE = re.compile(r"^(?:\d+|\d{1,3}(?:\.\d{3})+)$")
_COLUMNS = tuple("ABCDEFGH")
_TITLE = "ultimos movimientos"
_METADATA = (
    "saldo disponible",
    "saldo contable",
    "retenciones",
    "sobregiro disponible",
    "sobregiro utilizado",
    "linea de emergencia",
)
_HEADERS = {
    "A": "fecha transaccion",
    "B": "fecha contable",
    "C": "descripcion",
    "G": "cargo $",
    "H": "abono $",
}


class BciRecentMovementsParserError(Exception):
    """Expected safe parser failure with a stable sanitized code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class MalformedWorkbookError(BciRecentMovementsParserError):
    pass


class UnsupportedWorkbookError(BciRecentMovementsParserError):
    pass


class AmbiguousWorksheetError(BciRecentMovementsParserError):
    pass


@dataclass(frozen=True)
class _Cell:
    ref: str
    column: str
    row_number: int
    source: SourceCell


@dataclass(frozen=True)
class _Sheet:
    alias: str
    name: str
    ordinal: int
    visible: bool
    cells: Mapping[str, _Cell]
    populated_rows: tuple[int, ...]
    actual_max_row: int
    actual_max_column: int
    merged_ranges: tuple[str, ...]


def parse_bci_recent_movements_xlsx(
    source: Path | str | bytes | BinaryIO,
) -> ParseResult:
    """Parse one Recent Movements workbook without trusting worksheet dimensions."""

    try:
        data = _read_source(source)
        with ZipFile(BytesIO(data)) as package:
            sheets = _read_sheets(package)
            candidates = [sheet for sheet in sheets if sheet.visible and _matches_candidate(sheet)]
            if not candidates:
                raise UnsupportedWorkbookError("movement_header_not_found")
            if len(candidates) > 1:
                raise AmbiguousWorksheetError("ambiguous_statement_worksheets")
            return _parse_sheet(candidates[0])
    except (BadZipFile, ET.ParseError, KeyError, OSError, ValueError, IndexError) as error:
        if isinstance(error, BciRecentMovementsParserError):
            raise
        raise MalformedWorkbookError("xlsx_invalid") from error


def _read_source(source: Path | str | bytes | BinaryIO) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if isinstance(source, bytes):
        return source
    data = source.read()
    if not isinstance(data, bytes):
        raise TypeError("source must provide bytes")
    return data


def _read_sheets(package: ZipFile) -> tuple[_Sheet, ...]:
    workbook = ET.fromstring(package.read("xl/workbook.xml"))
    relationships = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: _relationship_target(relation.attrib["Target"])
        for relation in relationships.findall("p:Relationship", _NS)
    }
    result: list[_Sheet] = []
    for ordinal, sheet in enumerate(workbook.findall("m:sheets/m:sheet", _NS), 1):
        relation_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
        if relation_id not in targets:
            raise MalformedWorkbookError("worksheet_relationship_missing")
        worksheet_xml = ET.fromstring(package.read(targets[relation_id]))
        result.append(
            _read_sheet(
                worksheet_xml,
                name=sheet.attrib.get("name", ""),
                ordinal=ordinal,
                visible=sheet.attrib.get("state", "visible") == "visible",
            )
        )
    return tuple(result)


def _relationship_target(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else posixpath.join("xl", target)


def _read_sheet(root: ET.Element, *, name: str, ordinal: int, visible: bool) -> _Sheet:
    cells: dict[str, _Cell] = {}
    populated_rows: set[int] = set()
    max_row = 0
    max_column = 0
    for row in root.findall("m:sheetData/m:row", _NS):
        for cell in row.findall("m:c", _NS):
            ref = cell.attrib.get("r")
            if not ref:
                raise MalformedWorkbookError("cell_reference_missing")
            column, row_number = _split_ref(ref)
            source = _source_cell(cell)
            cells[ref] = _Cell(ref, column, row_number, source)
            if source.present and (source.value is not None or source.is_formula):
                populated_rows.add(row_number)
                max_row = max(max_row, row_number)
                max_column = max(max_column, _column_number(column))
    merged = tuple(
        merge.attrib["ref"]
        for merge in root.findall("m:mergeCells/m:mergeCell", _NS)
        if merge.attrib.get("ref")
    )
    return _Sheet(
        alias=f"S{ordinal}",
        name=name,
        ordinal=ordinal,
        visible=visible,
        cells=cells,
        populated_rows=tuple(sorted(populated_rows)),
        actual_max_row=max_row,
        actual_max_column=max_column,
        merged_ranges=merged,
    )


def _source_cell(cell: ET.Element) -> SourceCell:
    formula = cell.find("m:f", _NS)
    data_type = cell.attrib.get("t")
    if formula is not None:
        return SourceCell(
            value=formula.text or "",
            cell_type=data_type or "formula",
            is_formula=True,
            present=True,
        )
    if data_type == "inlineStr":
        value = "".join(text.text or "" for text in cell.findall("m:is//m:t", _NS))
        return SourceCell(value=value, cell_type=data_type, present=True)
    value_element = cell.find("m:v", _NS)
    if value_element is not None:
        return SourceCell(value=value_element.text or "", cell_type=data_type, present=True)
    return SourceCell(value=None, cell_type=data_type, present=True)


def _split_ref(ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    if match is None:
        raise MalformedWorkbookError("cell_reference_invalid")
    return match.group(1), int(match.group(2))


def _column_number(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _matches_candidate(sheet: _Sheet) -> bool:
    if sheet.name != "movimientos":
        return False
    if _text(sheet, "A1") != _TITLE:
        return False
    if sheet.merged_ranges.count("A1:H1") != 1:
        return False
    for row_number, expected in enumerate(_METADATA, 2):
        if _text(sheet, f"D{row_number}") != expected:
            return False
    if _header_row(sheet) != 8:
        return False
    if sheet.actual_max_row < 9 or sheet.actual_max_column > 8:
        return False
    if any(_range_is_outside_supported_shape(value, sheet.actual_max_row) for value in sheet.merged_ranges):
        return False
    return all(f"C{row}:F{row}" in sheet.merged_ranges for row in range(9, sheet.actual_max_row + 1))


def _range_is_outside_supported_shape(value: str, last_row: int) -> bool:
    if value == "A1:H1":
        return False
    match = re.fullmatch(r"C(\d+):F\1", value)
    return match is None or not 8 <= int(match.group(1)) <= last_row


def _header_row(sheet: _Sheet) -> int | None:
    labels = {column: _text(sheet, f"{column}8") for column in _COLUMNS}
    if any(labels[column] for column in ("D", "E", "F")):
        return None
    return 8 if all(labels.get(column) == value for column, value in _HEADERS.items()) else None


def _text(sheet: _Sheet, ref: str) -> str:
    cell = sheet.cells.get(ref)
    if cell is None or cell.source.is_formula or cell.source.value is None:
        return ""
    return _normalize_label(cell.source.value)


def _normalize_label(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().casefold()


def _parse_sheet(sheet: _Sheet) -> ParseResult:
    _validate_static_structure(sheet)
    records: list[SourceRecord] = []
    for row_number in range(1, sheet.actual_max_row + 1):
        raw = _raw_record(sheet, row_number)
        if row_number < 8:
            records.append(_ignored(raw, "metadata_row"))
        elif row_number == 8:
            records.append(_ignored(raw, "header_row"))
        else:
            records.append(_parse_transaction(raw, sheet, records))
    return ParseResult(
        status=ParserStatus.RECOGNIZED,
        source_variant=SOURCE_VARIANT,
        parser_version=PARSER_VERSION,
        contract_version=CONTRACT_VERSION,
        sheet_alias=sheet.alias,
        worksheet_name=sheet.name,
        worksheet_ordinal=sheet.ordinal,
        actual_max_row=sheet.actual_max_row,
        actual_max_column=sheet.actual_max_column,
        records=tuple(records),
    )


def _validate_static_structure(sheet: _Sheet) -> None:
    if sheet.populated_rows != tuple(range(1, sheet.actual_max_row + 1)):
        # Rows such as the observed metadata/header rows must be populated; an
        # empty row inside the discovered extent would make the boundary ambiguous.
        raise UnsupportedWorkbookError("unexpected_empty_row")
    for cell in sheet.cells.values():
        if cell.source.is_formula and cell.row_number <= 8:
            raise UnsupportedWorkbookError("formula_unsupported")
        if cell.source.value is not None and cell.source.cell_type != "inlineStr":
            if cell.row_number <= 8:
                raise UnsupportedWorkbookError("cell_type_unsupported")


def _raw_record(sheet: _Sheet, row_number: int) -> SourceRecord:
    raw_cells = {
        column: sheet.cells.get(f"{column}{row_number}", _Cell(
            f"{column}{row_number}", column, row_number, SourceCell()
        )).source
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
        provenance=_provenance(sheet, row_number),
    )


def _provenance(sheet: _Sheet, row_number: int) -> dict[str, object]:
    return {
        "source_variant": SOURCE_VARIANT,
        "contract_version": CONTRACT_VERSION,
        "parser_version": PARSER_VERSION,
        "sheet_alias": sheet.alias,
        "worksheet_name": sheet.name,
        "worksheet_ordinal": sheet.ordinal,
        "row_number": row_number,
        "source_fields": {
            "transaction_date": {"column": "A", "cell_type": _cell_type(sheet, f"A{row_number}")},
            "accounting_date": {"column": "B", "cell_type": _cell_type(sheet, f"B{row_number}")},
            "description": {
                "columns": ("C", "D", "E", "F"),
                "merged_range": f"C{row_number}:F{row_number}",
                "cell_type": _cell_type(sheet, f"C{row_number}"),
            },
            "amount": {
                "columns": ("G", "H"),
                "cell_types": {
                    "G": _cell_type(sheet, f"G{row_number}"),
                    "H": _cell_type(sheet, f"H{row_number}"),
                },
            },
        },
    }


def _cell_type(sheet: _Sheet, ref: str) -> str | None:
    cell = sheet.cells.get(ref)
    return cell.source.cell_type if cell is not None else None


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


def _parse_transaction(raw: SourceRecord, sheet: _Sheet, records: Iterable[SourceRecord]) -> SourceRecord:
    cells = raw.raw_cells
    if any(cells[column].is_formula for column in _COLUMNS):
        return _rejected(raw, "formula_unsupported")
    if any(
        cells[column].value is not None and cells[column].cell_type != "inlineStr"
        for column in _COLUMNS
    ):
        return _rejected(raw, "cell_type_unsupported")

    transaction_date = _parse_date(cells["A"].value)
    accounting_date = _parse_date(cells["B"].value)
    errors: list[str] = []
    if transaction_date is None:
        errors.append("date_invalid")
    if accounting_date is None:
        errors.append("accounting_date_invalid")

    description = _clean_optional(cells["C"].value)
    cargo_present = _present(cells["G"])
    abono_present = _present(cells["H"])
    if cargo_present == abono_present:
        errors.append("direction_xor_invalid")
        direction = None
        amount = None
    else:
        direction = "cargo" if cargo_present else "abono"
        amount_cell = cells["G"] if cargo_present else cells["H"]
        amount = _parse_amount(amount_cell.value)
        if amount is None:
            errors.append("amount_invalid")

    prior_dates = [record.transaction_date for record in records if record.outcome is RowOutcome.PARSED]
    if transaction_date is not None and prior_dates and transaction_date > prior_dates[-1]:
        errors.append("transaction_date_order_invalid")
    if errors:
        return _rejected(raw, *errors)
    assert transaction_date is not None and accounting_date is not None and amount is not None
    return SourceRecord(
        raw_record_id=raw.raw_record_id,
        sheet_alias=raw.sheet_alias,
        worksheet_name=raw.worksheet_name,
        worksheet_ordinal=raw.worksheet_ordinal,
        row_number=raw.row_number,
        raw_cells=raw.raw_cells,
        outcome=RowOutcome.PARSED,
        transaction_date=transaction_date,
        accounting_date=accounting_date,
        source_description=description,
        source_direction=direction,
        source_amount=amount,
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


def _present(cell: SourceCell) -> bool:
    return cell.present and cell.value is not None and str(cell.value).strip() != ""


def _clean_optional(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_date(value: object | None) -> date | None:
    text = _clean_optional(value)
    if text is None or not _DATE_RE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_amount(value: object | None) -> Decimal | None:
    text = _clean_optional(value)
    if text is None or not _MONEY_RE.fullmatch(text):
        return None
    try:
        integer = text.replace(".", "")
        return Decimal(integer).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
