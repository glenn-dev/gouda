"""Wholly synthetic BCI Historical PDFs for deterministic contract tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal


def synthetic_bci_historical_pdf(
    *,
    rows: tuple[dict[str, object], ...] = (),
    period_start: date = date(2026, 1, 1),
    period_end: date = date(2026, 1, 31),
    source_account_id: str = "900000000001",
    opening_balance: int | Decimal = Decimal("100000"),
    closing_override: int | None = None,
    printed_total_debits_override: int | None = None,
    printed_total_credits_override: int | None = None,
    omit_summary_operand: str | None = None,
    wrong_product: bool = False,
    summary_period_override: tuple[date, date] | None = None,
    currency_text: str = "PESOS",
    omit_header_period: bool = False,
    header_variant: str | None = None,
    duplicate_summary_operand: str | None = None,
    page_size: tuple[float, float] = (612, 792),
) -> bytes:
    """Build a small native-text PDF using the frozen BCI geometry profile."""

    normalized_rows = []
    balance = Decimal(str(opening_balance))
    for index, row in enumerate(rows):
        accounting_date = row.get("date", period_start + timedelta(days=index))
        debit = Decimal(str(row.get("debit", "0")))
        credit = Decimal(str(row.get("credit", "0")))
        if "balance" in row:
            balance = Decimal(str(row["balance"]))
        else:
            balance += credit - debit
        normalized_rows.append({
            "date": accounting_date,
            "branch": row.get("branch", "SYNTH"),
            "description": row.get("description", f"Synthetic row {index + 1}"),
            "reference": row.get("reference"),
            "debit": debit,
            "credit": credit,
            "debit_text": row.get("debit_text"),
            "credit_text": row.get("credit_text"),
            "emit_debit_zero": row.get("emit_debit_zero", False),
            "emit_credit_zero": row.get("emit_credit_zero", False),
            "balance": balance,
        })
    opening = Decimal(str(opening_balance))
    total_debits = sum((row["debit"] for row in normalized_rows), Decimal("0"))
    total_credits = sum((row["credit"] for row in normalized_rows), Decimal("0"))
    printed_debits = Decimal(str(printed_total_debits_override)) if printed_total_debits_override is not None else total_debits
    printed_credits = Decimal(str(printed_total_credits_override)) if printed_total_credits_override is not None else total_credits
    closing = Decimal(str(closing_override)) if closing_override is not None else opening + total_credits - total_debits
    pages = []
    chunks = [normalized_rows[index:index + 14] for index in range(0, len(normalized_rows), 14)] or [[]]
    for page_number, chunk in enumerate(chunks, 1):
        lines: list[tuple[float, float, str]] = []
        if page_number == 1:
            product = "BCI CARTOLA DE CUENTA CORRIENTE" if not wrong_product else "OTHER CARTOLA DE CUENTA CORRIENTE"
            lines += [(24, 772, "SYNTHETIC HEADER"), (277, 772, product)]
            lines += [(194, 780, "CARTOLA DE CUENTA CORRIENTE"), (456, 780, "CARTOLA N°"), (557, 780, "700001")]
            lines += [(414, 760, "N° CUENTA"), (463, 760, source_account_id), (560, 760, f"MONEDA {currency_text}")]
            if not omit_header_period:
                lines += [(414, 740, "PERIODO"), (460, 740, _date_text(period_start, '-')), (512, 740, "al"), (525, 740, _date_text(period_end, '-'))]
        variant = None if header_variant == "continuation_wrong" and page_number == 1 else header_variant
        lines += _table_header(variant)
        for offset, row in enumerate(chunk):
            top = 95 + offset * 34
            lines += _row_lines(row, top)
        if page_number == len(chunks):
            summary_top = 95 + len(chunk) * 34 + 24
            lines += [(46, 792 - summary_top, "Resumen del Periodo")]
            lines += [(358, 792 - summary_top - 14, "Total Cargos"), (431, 792 - summary_top - 14, "Total Abonos"), (498, 792 - summary_top - 14, "Saldo Contable")]
            summary_start, summary_end = summary_period_override or (period_start, period_end)
            lines += [(50, 792 - summary_top - 34, "Periodo"), (120, 792 - summary_top - 34, _date_text(summary_start, '-')), (190, 792 - summary_top - 34, "al"), (212, 792 - summary_top - 34, _date_text(summary_end, '-'))]
            if duplicate_summary_operand == "debits":
                lines += [(358, 792 - summary_top - 20, "Total Cargos")]
            if duplicate_summary_operand == "credits":
                lines += [(431, 792 - summary_top - 20, "Total Abonos")]
            if duplicate_summary_operand == "opening":
                lines += [(292, 792 - summary_top - 20, "Saldo Anterior")]
            if duplicate_summary_operand == "closing":
                lines += [(498, 792 - summary_top - 20, "Saldo Contable")]
            values = {
                "opening": _money_text(opening),
                "debits": _money_text(printed_debits),
                "credits": _money_text(printed_credits),
                "closing": _money_text(closing),
            }
            if omit_summary_operand == "opening":
                values["opening"] = ""
            if omit_summary_operand == "debits":
                values["debits"] = ""
            if omit_summary_operand == "credits":
                values["credits"] = ""
            if omit_summary_operand == "closing":
                values["closing"] = ""
            lines += [(292, 792 - summary_top - 28, "Saldo Anterior"), (302, 792 - summary_top - 48, values["opening"]), (377, 792 - summary_top - 48, values["debits"]), (454, 792 - summary_top - 48, values["credits"]), (546, 792 - summary_top - 48, values["closing"])]
        pages.append(lines)
    return _pdf(pages, page_size=page_size)


def _table_header(variant: str | None = None) -> list[tuple[float, float, str]]:
    header = [
        (48, 717, "Fecha"),
        (101, 717, "Sucursal"),
        (188, 717, "Descripcion"),
        (287, 717, "Documento"),
        (363, 717, "Cargos"),
        (441, 717, "Abonos"),
        (507, 717, "Saldo Diario"),
    ]
    if variant == "reordered":
        header[1] = (101, 717, "Descripcion")
        header[2] = (188, 717, "Sucursal")
    elif variant == "continuation_wrong":
        header[4] = (390, 717, "Cargos")
    return header


def _row_lines(row: dict[str, object], top: float) -> list[tuple[float, float, str]]:
    lines = [
        (44, 792 - top, _date_text(row["date"], "/")),
        (101, 792 - top, str(row["branch"])),
        (154, 792 - top, str(row["description"])),
    ]
    if row["reference"] is not None:
        lines.append((309, 792 - top, str(row["reference"])))
    if row["debit"] or row["debit_text"] is not None or row["emit_debit_zero"]:
        lines.append((391, 792 - top, str(row["debit_text"]) if row["debit_text"] is not None else _money_text(row["debit"])))
    if row["credit"] or row["credit_text"] is not None or row["emit_credit_zero"]:
        lines.append((464, 792 - top, str(row["credit_text"]) if row["credit_text"] is not None else _money_text(row["credit"])))
    lines.append((547, 792 - top, _money_text(row["balance"])))
    return lines


def _date_text(value: object, separator: str) -> str:
    if not isinstance(value, date):
        raise TypeError("synthetic date must be date")
    return value.strftime(f"%d{separator}%m{separator}%Y")


def _money_text(value: object) -> str:
    return str(int(Decimal(str(value))))


def _pdf(pages: list[list[tuple[float, float, str]]], *, page_size: tuple[float, float] = (612, 792)) -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append((f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>").encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, lines in enumerate(pages):
        content = b"".join(_text_command(x, y, text) for x, y, text in lines)
        stream = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"endstream"
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_size[0]} {page_size[1]}] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + index * 2} 0 R >>".encode())
        objects.append(stream)
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode())
        result.extend(obj)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    result.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def _text_command(x: float, y: float, text: str) -> bytes:
    escaped = str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    font_size = 6 if 730 < y < 770 else 9
    return f"BT /F1 {font_size} Tf 1 0 0 1 {x} {y} Tm ({escaped}) Tj ET\n".encode()
