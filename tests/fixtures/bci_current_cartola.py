from __future__ import annotations

from dataclasses import replace

from gouda.bci_current_cartola_xls.parser import _Sheet
from gouda.bci_current_cartola_xls.types import SourceCell


METADATA = (
    "Saldo Disponible",
    "Saldo Contable",
    "Retenciones",
    "Sobregiro Disponible",
    "Sobregiro Utilizado",
    "Linea de Emergencia",
)
HEADERS = ("Fecha", "Descripción", "Serie", "Monto $", "Saldo Contable $")
COLUMNS = tuple("ABCDE")


def text_cell(value: str = "") -> SourceCell:
    return SourceCell(value=value, cell_type="text", present=True)


def empty_cell() -> SourceCell:
    return SourceCell(value=None, cell_type="empty", present=False)


def synthetic_current_cartola_sheet(
    *,
    transactions: list[dict[str, object | None]] | None = None,
    title: str = "Movimientos de su cuenta",
    metadata: tuple[str, ...] = METADATA,
    headers: tuple[str, ...] = HEADERS,
    title_merge: str = "A1:E1",
    name: str = "Synthetic Current Sheet",
    ordinal: int = 1,
    visible: bool = True,
) -> _Sheet:
    transactions = transactions or [
        {
            "date": "25-08-2031",
            "description": "  Synthetic purchase  ",
            "series": "opaque-A",
            "amount": "-1.234",
            "balance": "8.000",
        },
        {
            "date": "24-08-2031",
            "description": "Synthetic deposit",
            "series": "opaque-B",
            "amount": "500",
            "balance": "8.500",
        },
    ]
    rows: dict[int, dict[str, SourceCell]] = {
        row_number: {column: empty_cell() for column in COLUMNS}
        for row_number in range(1, 10 + len(transactions))
    }
    rows[1]["A"] = text_cell(title)
    for row_number, label in enumerate(metadata, 2):
        rows[row_number]["B"] = text_cell(label)
        rows[row_number]["C"] = text_cell("Synthetic snapshot")
    for column, header in zip(COLUMNS, headers):
        rows[9][column] = text_cell(header)
    for row_number, transaction in enumerate(transactions, 10):
        rows[row_number] = {
            "A": _source_cell(transaction.get("date")),
            "B": _source_cell(transaction.get("description")),
            "C": _source_cell(transaction.get("series")),
            "D": _source_cell(transaction.get("amount")),
            "E": _source_cell(transaction.get("balance")),
        }
    return _rebuild_sheet(
        _Sheet(
            alias=f"S{ordinal}",
            name=name,
            ordinal=ordinal,
            visible=visible,
            rows=rows,
            populated_rows=(),
            populated_columns=(),
            actual_max_row=0,
            actual_max_column=0,
            physical_nrows=max(rows),
            physical_ncols=5,
            merged_ranges=(title_merge,),
        )
    )


def with_cell(
    sheet: _Sheet,
    row_number: int,
    column: str,
    cell: SourceCell,
) -> _Sheet:
    rows = {number: dict(row) for number, row in sheet.rows.items()}
    rows.setdefault(row_number, {name: empty_cell() for name in COLUMNS})[column] = cell
    return _rebuild_sheet(replace(sheet, rows=rows, physical_nrows=max(sheet.physical_nrows, row_number)))


def _source_cell(value: object | None) -> SourceCell:
    if isinstance(value, SourceCell):
        return value
    if value is None:
        return empty_cell()
    return text_cell(str(value))


def _rebuild_sheet(sheet: _Sheet) -> _Sheet:
    populated_rows: set[int] = set()
    populated_columns: set[int] = set()
    max_row = 0
    max_column = 0
    for row_number, row in sheet.rows.items():
        for column, cell in row.items():
            if _populated(cell):
                column_number = ord(column) - ord("A") + 1
                populated_rows.add(row_number)
                populated_columns.add(column_number)
                max_row = max(max_row, row_number)
                max_column = max(max_column, column_number)
    return replace(
        sheet,
        populated_rows=tuple(sorted(populated_rows)),
        populated_columns=tuple(sorted(populated_columns)),
        actual_max_row=max_row,
        actual_max_column=max_column,
    )


def _populated(cell: SourceCell) -> bool:
    return cell.is_formula or (
        cell.present
        and cell.cell_type not in ("empty", "blank")
        and cell.value is not None
        and str(cell.value) != ""
    )
