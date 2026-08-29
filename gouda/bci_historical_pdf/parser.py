"""Fail-closed BCI Historical current-account PDF v0.1 parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable

from .extraction import (
    EXTRACTION_PROFILE_VERSION,
    GIR_VERSION,
    BciHistoricalPdfGir,
    BoundingBox,
    Line,
    Page,
    Token,
    extract_bci_historical_pdf,
    recognition_key,
)
from .types import (
    BciCheckStatus,
    BciHistoricalParseResult,
    BciHistoricalReconciliation,
    BciHistoricalReconciliationCheck,
    BciHistoricalSourceRecord,
    BciHistoricalStatementMetadata,
    BciParserStatus,
    BciReconciliationStatus,
    BciRowOutcome,
    FieldProvenance,
)


PARSER_VERSION = "bci-historical-current-account-pdf-v1"
SOURCE_VARIANT = "bci_historical_current_account_pdf"
_TOLERANCE = Decimal("3.00")
_DATE_RE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_PERIOD_RE = re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{4})(?!\d)")
_DATE_LIKE_RE = re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{4}(?!\d)")
_INTEGER_RE = re.compile(r"\d+")
_MONEY_RE = re.compile(r"\d+|\d{1,3}(?:\.\d{3})+")
_BALANCE_RE = re.compile(r"-?(?:\d+|\d{1,3}(?:\.\d{3})+)")
_HEADER_LABELS = ("fecha", "sucursal", "descripcion", "documento", "cargos", "abonos", "saldo", "diario")
_BANDS = {
    "date": (Decimal("40"), Decimal("94")),
    "branch": (Decimal("94"), Decimal("150")),
    "description": (Decimal("150"), Decimal("286")),
    "reference": (Decimal("286"), Decimal("360")),
    "debit": (Decimal("360"), Decimal("426")),
    "credit": (Decimal("426"), Decimal("505")),
    "balance": (Decimal("505"), Decimal("606")),
}


class BciHistoricalParserError(Exception):
    """Expected document-fatal parser error with a stable code only."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _LineRef:
    page: Page
    line: Line
    tokens: tuple[Token, ...]

    @property
    def key(self) -> str:
        return recognition_key(" ".join(token.text for token in self.tokens))


@dataclass(frozen=True)
class _RowGroup:
    page: Page
    refs: tuple[_LineRef, ...]
    ordinal: int


@dataclass(frozen=True)
class _SummaryValue:
    value: Decimal
    ref: _LineRef
    tokens: tuple[Token, ...]


def parse_bci_historical_pdf_gir(gir: BciHistoricalPdfGir) -> BciHistoricalParseResult:
    try:
        return _parse_gir(gir)
    except BciHistoricalParserError as error:
        return _fatal(error.code, gir=gir)
    except Exception:
        return _fatal("parser_unexpected", gir=gir)


def parse_bci_historical_pdf(source) -> BciHistoricalParseResult:
    try:
        return parse_bci_historical_pdf_gir(extract_bci_historical_pdf(source))
    except Exception as error:
        code = getattr(error, "code", None) or "pdf_invalid"
        return _fatal(code)


def _parse_gir(gir: BciHistoricalPdfGir) -> BciHistoricalParseResult:
    if not isinstance(gir, BciHistoricalPdfGir) or gir.gir_version != GIR_VERSION or gir.extraction_profile_version != EXTRACTION_PROFILE_VERSION:
        raise BciHistoricalParserError("unsupported_gir_profile")
    if not gir.pages:
        raise BciHistoricalParserError("native_text_required")
    if tuple(page.ordinal for page in gir.pages) != tuple(range(1, len(gir.pages) + 1)):
        raise BciHistoricalParserError("page_number_invalid")
    refs_by_page = [_line_refs(page) for page in gir.pages]
    metadata = _parse_metadata(refs_by_page[0])
    header_refs = [_find_table_header(refs) for refs in refs_by_page]
    if any(ref is None for ref in header_refs):
        raise BciHistoricalParserError("transaction_header_missing")
    assert all(ref is not None for ref in header_refs)
    header_refs = [ref for ref in header_refs if ref is not None]
    if not _compatible_headers(header_refs):
        raise BciHistoricalParserError("unsupported_financial_table_geometry")
    summary_top, summary_values, metadata = _parse_summary(refs_by_page[-1], metadata)
    groups, ignored = _row_groups(refs_by_page, header_refs, summary_top)
    records: list[BciHistoricalSourceRecord] = list(ignored)
    records.append(_ignored(_summary_context(refs_by_page[-1]), "period_summary"))
    last_date: date | None = None
    for group in groups:
        record = _parse_group(group, metadata, last_date)
        records.append(record)
        if record.outcome is BciRowOutcome.PARSED:
            last_date = record.accounting_date
    records.sort(key=lambda record: (record.page_ordinal, record.line_ordinals[0] if record.line_ordinals else 0, record.source_row_ordinal if record.source_row_ordinal else 0))
    reconciliation = _reconcile(metadata, records, summary_values)
    return BciHistoricalParseResult(
        status=BciParserStatus.RECOGNIZED,
        provider="BCI",
        product="current_account",
        source_variant=SOURCE_VARIANT,
        parser_version=PARSER_VERSION,
        gir_version=gir.gir_version,
        extraction_profile_version=gir.extraction_profile_version,
        metadata=metadata,
        records=tuple(records),
        reconciliation=reconciliation,
    )


def _fatal(code: str, *, gir: BciHistoricalPdfGir | None = None) -> BciHistoricalParseResult:
    return BciHistoricalParseResult(
        status=BciParserStatus.FATAL,
        provider="BCI",
        product="current_account",
        source_variant=None,
        parser_version=PARSER_VERSION,
        gir_version=gir.gir_version if gir else GIR_VERSION,
        extraction_profile_version=gir.extraction_profile_version if gir else EXTRACTION_PROFILE_VERSION,
        metadata=None,
        records=(),
        reconciliation=BciHistoricalReconciliation(BciReconciliationStatus.NOT_APPLICABLE, {}),
        errors=(code,),
    )


def _line_refs(page: Page) -> list[_LineRef]:
    token_map = {token.extraction_ordinal: token for token in page.tokens}
    return [_LineRef(page, line, tuple(token_map[ordinal] for ordinal in line.token_ordinals)) for line in page.lines]


def _parse_metadata(refs: list[_LineRef]) -> BciHistoricalStatementMetadata:
    table_header = _find_table_header(refs)
    metadata_limit = table_header.line.bbox.y0 if table_header is not None else Decimal("210")
    top = [ref for ref in refs if ref.line.bbox.y0 < metadata_limit]
    product = [ref for ref in top if "bci" in ref.key and "cartola" in ref.key and "cuenta" in ref.key and "corriente" in ref.key]
    if len(product) != 1:
        raise BciHistoricalParserError("source_identity_mismatch")
    statement_candidates = [ref for ref in top if "cartola" in ref.key and any(_INTEGER_RE.fullmatch(token.text) and token.bbox.x0 >= Decimal("530") for token in ref.tokens)]
    account_candidates = [ref for ref in top if "cuenta" in ref.key and "moneda" in ref.key and any(_INTEGER_RE.fullmatch(token.text) and Decimal("440") <= token.bbox.x0 <= Decimal("510") for token in ref.tokens)]
    period_candidates = [ref for ref in top if "periodo" in ref.key and len(_PERIOD_RE.findall(ref.key)) == 2]
    currency_candidates = [ref for ref in top if "moneda" in ref.key and any(recognition_key(token.text) in {"pesos", "clp"} for token in ref.tokens)]
    if len(statement_candidates) != 1:
        raise BciHistoricalParserError("statement_identifier_invalid")
    if len(account_candidates) != 1:
        raise BciHistoricalParserError("account_identity_invalid")
    if len(period_candidates) != 1:
        raise BciHistoricalParserError("period_missing")
    if len(currency_candidates) != 1:
        raise BciHistoricalParserError("currency_missing")
    statement_id = _single_token(statement_candidates[0], lambda token: _INTEGER_RE.fullmatch(token.text) is not None, x0=Decimal("530"))
    source_account_id = _single_token(account_candidates[0], lambda token: _INTEGER_RE.fullmatch(token.text) is not None, x0=Decimal("440"), x1=Decimal("510"))
    period_values = _PERIOD_RE.findall(period_candidates[0].key)
    start = _make_date(period_values[0], "period_invalid")
    end = _make_date(period_values[1], "period_invalid")
    if start > end:
        raise BciHistoricalParserError("period_invalid")
    fields = {
        "statement_id": _provenance(statement_candidates[0], "statement_identifier"),
        "source_account_id": _provenance(account_candidates[0], "source_account_identity"),
        "period": _provenance(period_candidates[0], "statement_period"),
        "currency": _provenance(currency_candidates[0], "statement_currency"),
    }
    return BciHistoricalStatementMetadata(statement_id, start, end, "CLP", source_account_id, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), fields)


def _single_token(ref: _LineRef, predicate, *, x0: Decimal, x1: Decimal | None = None) -> str:
    candidates = [token.text for token in ref.tokens if token.bbox.x0 >= x0 and (x1 is None or token.bbox.x0 <= x1) and predicate(token)]
    if len(candidates) != 1:
        raise BciHistoricalParserError("metadata_ambiguous")
    return candidates[0].strip()


def _find_table_header(refs: list[_LineRef]) -> _LineRef | None:
    for ref in refs:
        if ref.line.bbox.y0 > Decimal("280"):
            continue
        labels = set(ref.key.split())
        if all(label in labels for label in _HEADER_LABELS):
            return ref
    return None


def _compatible_headers(headers: list[_LineRef]) -> bool:
    if not headers:
        return False
    expected = {"fecha": Decimal("48"), "sucursal": Decimal("101"), "descripcion": Decimal("188"), "documento": Decimal("287"), "cargos": Decimal("363"), "abonos": Decimal("441"), "saldo": Decimal("507")}
    for ref in headers:
        for label, expected_x in expected.items():
            token = next((token for token in ref.tokens if recognition_key(token.text) == label), None)
            if token is None or abs(token.bbox.x0 - expected_x) > _TOLERANCE:
                return False
    return True


def _parse_summary(refs: list[_LineRef], metadata: BciHistoricalStatementMetadata) -> tuple[Decimal, dict[str, _SummaryValue | None], BciHistoricalStatementMetadata]:
    context = _summary_context(refs)
    following = [ref for ref in refs if ref.line.bbox.y0 >= context.line.bbox.y0]
    summary_period = _summary_period(following, context)
    if summary_period is None:
        raise BciHistoricalParserError("period_summary_missing")
    if summary_period != (metadata.period_start, metadata.period_end):
        raise BciHistoricalParserError("period_summary_mismatch")
    opening = _summary_money(following, (Decimal("280"), Decimal("350")), ("saldo", "anterior"))
    debits = _summary_money(following, (Decimal("350"), Decimal("426")), ("total", "cargos"))
    credits = _summary_money(following, (Decimal("426"), Decimal("505")), ("total", "abonos"))
    closing = _summary_money(following, (Decimal("535"), Decimal("605")), ("saldo", "contable"))
    values = {"opening_balance": opening, "printed_total_debits": debits, "printed_total_credits": credits, "closing_balance": closing}
    metadata = BciHistoricalStatementMetadata(
        metadata.statement_id,
        metadata.period_start,
        metadata.period_end,
        metadata.currency,
        metadata.source_account_id,
        opening.value if opening else None,
        debits.value if debits else None,
        credits.value if credits else None,
        closing.value if closing else None,
        {
            **metadata.fields,
            **{
                name: _provenance_tokens(value.ref.page, (value.ref,), list(value.tokens), name)
                for name, value in values.items()
                if value is not None
            },
        },
    )
    return context.line.bbox.y0, values, metadata


def _summary_context(refs: list[_LineRef]) -> _LineRef:
    summary_context = [ref for ref in refs if "resumen" in ref.key and "periodo" in ref.key]
    if len(summary_context) != 1:
        raise BciHistoricalParserError("period_summary_missing")
    return summary_context[0]


def _summary_period(refs: list[_LineRef], context: _LineRef) -> tuple[date, date] | None:
    candidates = [
        token
        for ref in refs
        if ref.line.bbox.y0 - context.line.bbox.y0 <= Decimal("70")
        for token in ref.tokens
        if Decimal("20") <= token.bbox.x0 < Decimal("280")
    ]
    text = " ".join(token.text for token in candidates)
    text = re.sub(r"\s*-\s*", "-", text)
    matches = _PERIOD_RE.findall(text)
    if len(matches) != 2:
        return None
    return _make_date(matches[0], "period_summary_invalid"), _make_date(matches[1], "period_summary_invalid")


def _summary_money(refs: list[_LineRef], band: tuple[Decimal, Decimal], labels: tuple[str, ...]) -> _SummaryValue | None:
    grammar = _BALANCE_RE if labels in (("saldo", "anterior"), ("saldo", "contable")) else _MONEY_RE
    label_refs = [ref for ref in refs if all(label in ref.key.split() for label in labels)]
    if not label_refs:
        return None
    if len(label_refs) != 1:
        raise BciHistoricalParserError("period_summary_ambiguous")
    label_ref = label_refs[0]
    value_ref = label_ref
    tokens = [token for token in value_ref.tokens if band[0] <= token.bbox.x0 < band[1] and grammar.fullmatch(token.text)]
    if len(tokens) != 1:
        # Summary values are printed on the next physical line in the observed family.
        nearby = [ref for ref in refs if 0 <= ref.line.bbox.y0 - label_ref.line.bbox.y1 <= Decimal("30")]
        matches = [
            (ref, token)
            for ref in nearby
            for token in ref.tokens
            if band[0] <= token.bbox.x0 < band[1] and grammar.fullmatch(token.text)
        ]
        if len(matches) > 1:
            raise BciHistoricalParserError("period_summary_ambiguous")
        if not matches:
            return None
        value_ref, token = matches[0]
        tokens = [token]
    allow_negative = labels in (("saldo", "anterior"), ("saldo", "contable"))
    value = _parse_money(tokens[0].text, allow_negative=allow_negative)
    if value in (_INVALID, _OVERFLOW):
        return None
    return _SummaryValue(value, value_ref, tuple(tokens))


def _row_groups(refs_by_page: list[list[_LineRef]], headers: list[_LineRef], summary_top: Decimal) -> tuple[list[_RowGroup], list[BciHistoricalSourceRecord]]:
    groups: list[_RowGroup] = []
    ignored: list[BciHistoricalSourceRecord] = []
    ordinal = 0
    for page_refs, header in zip(refs_by_page, headers):
        active: list[_LineRef] = []
        page_start = header.line.bbox.y1
        page_summary_top = summary_top if header.page.ordinal == len(refs_by_page) else Decimal("9999")
        for ref in page_refs:
            if ref is header or ref.line.bbox.y0 <= page_start or ref.line.bbox.y0 >= page_summary_top:
                continue
            if _row_candidate_start(ref):
                if active:
                    ordinal += 1
                    groups.append(_RowGroup(page_refs[0].page, tuple(active), ordinal))
                active = [ref]
                continue
            if active and _inside_table(ref):
                active.append(ref)
                continue
            if active:
                ordinal += 1
                groups.append(_RowGroup(page_refs[0].page, tuple(active), ordinal))
                active = []
        if active:
            ordinal += 1
            groups.append(_RowGroup(page_refs[0].page, tuple(active), ordinal))
        ignored.append(_ignored(header, "table_header" if header.page.ordinal == 1 else "page_continuation"))
    return groups, ignored


def _parse_group(group: _RowGroup, metadata: BciHistoricalStatementMetadata, previous_date: date | None) -> BciHistoricalSourceRecord:
    tokens = [token for ref in group.refs for token in ref.tokens]
    all_lines = tuple(ref.line.ordinal for ref in group.refs)
    all_tokens = tuple(token.extraction_ordinal for token in tokens)
    fields = {"row": _provenance_group(group, "transaction_row")}
    values: dict[str, object] = {}
    for name, band in _BANDS.items():
        selected = [token for token in tokens if band[0] <= token.bbox.x0 < band[1]]
        if selected:
            fields[name] = _provenance_tokens(group.page, group.refs, selected, name)
        values[name] = selected
    date_tokens = values["date"]
    source_date_text = " ".join(token.text for token in date_tokens).strip() if date_tokens else None
    accounting_date = _parse_transaction_date(source_date_text)
    branch = _join_text(values["branch"])
    description = _join_text(values["description"])
    reference = _join_text(values["reference"])
    debit = _field_money(values["debit"], allow_negative=False)
    credit = _field_money(values["credit"], allow_negative=False)
    balance = _field_money(values["balance"], allow_negative=True)
    reason = None
    if accounting_date is None:
        reason = "date_invalid"
    elif accounting_date < metadata.period_start or accounting_date > metadata.period_end:
        reason = "date_outside_period"
    elif previous_date is not None and accounting_date < previous_date:
        reason = "date_order_invalid"
    elif len(values["debit"]) > 1 or len(values["credit"]) > 1 or len(values["balance"]) > 1:
        reason = "row_geometry_ambiguous"
    elif debit is _OVERFLOW or credit is _OVERFLOW or balance is _OVERFLOW:
        reason = "money_precision_overflow"
    elif debit is _INVALID or credit is _INVALID or balance is _INVALID:
        reason = "amount_invalid" if debit is _INVALID or credit is _INVALID else "running_balance_invalid"
    elif debit is None and credit is None:
        reason = "amount_missing"
    elif debit is not None and credit is not None:
        reason = "amount_both_sides"
    elif (debit is not None and debit <= 0) or (credit is not None and credit <= 0):
        reason = "negative_directional_amount" if (debit is not None and debit < 0) or (credit is not None and credit < 0) else "zero_amount_unsupported"
    elif balance is None:
        reason = "running_balance_missing"
    if reason:
        return BciHistoricalSourceRecord(BciRowOutcome.REJECTED, reason, group.page.ordinal, group.ordinal, all_lines, all_tokens, fields, source_date_text, accounting_date, None, branch, description, reference, debit if debit not in (_INVALID, _OVERFLOW) else None, credit if credit not in (_INVALID, _OVERFLOW) else None, None, balance if balance not in (_INVALID, _OVERFLOW) else None, metadata.currency)
    signed = (credit or Decimal("0")) - (debit or Decimal("0"))
    return BciHistoricalSourceRecord(BciRowOutcome.PARSED, "transaction_parsed", group.page.ordinal, group.ordinal, all_lines, all_tokens, fields, source_date_text, accounting_date, None, branch, description, reference, debit, credit, signed, balance, metadata.currency)


_INVALID = object()
_OVERFLOW = object()


def _parse_transaction_date(text: str | None) -> date | None:
    if text is None or _DATE_RE.fullmatch(text) is None:
        return None
    day, month, year = _DATE_RE.fullmatch(text).groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _field_money(tokens: list[Token], *, allow_negative: bool):
    if not tokens:
        return None
    if len(tokens) != 1:
        return _INVALID
    text = tokens[0].text
    if not allow_negative and text.startswith("-"):
        return _parse_money(text, allow_negative=True)
    return _parse_money(text, allow_negative=allow_negative)


def _parse_money(text: str, *, allow_negative: bool):
    grammar = _BALANCE_RE if allow_negative else _MONEY_RE
    if grammar.fullmatch(text) is None:
        return _INVALID
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    if "." in digits and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", digits):
        return _INVALID
    try:
        # BCI prints whole Chilean pesos with optional dot thousands groups;
        # Gouda stores the same magnitude at an exact two-decimal scale.
        value = Decimal(digits.replace(".", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return _INVALID
    if negative:
        value = -value
    try:
        from gouda.ledger.validation import validate_exact_money
        validate_exact_money(value)
    except Exception:
        return _OVERFLOW
    return value


def _reconcile(metadata: BciHistoricalStatementMetadata, records: list[BciHistoricalSourceRecord], summary: dict[str, _SummaryValue | None]) -> BciHistoricalReconciliation:
    parsed = [record for record in records if record.outcome is BciRowOutcome.PARSED]
    rejected = any(record.outcome is BciRowOutcome.REJECTED for record in records)
    all_operands = {"opening_balance": metadata.opening_balance, "printed_total_debits": metadata.printed_total_debits, "printed_total_credits": metadata.printed_total_credits, "closing_balance": metadata.closing_balance}
    operands = {name: value for name, value in all_operands.items() if value is not None}
    missing = tuple(name for name, value in all_operands.items() if value is None)
    checks: dict[str, BciHistoricalReconciliationCheck] = {}
    balance_fields = {name: metadata.fields[name] for name in ("opening_balance", "closing_balance") if name in metadata.fields}
    summary_fields = {name: metadata.fields[name] for name in ("opening_balance", "printed_total_debits", "printed_total_credits", "closing_balance") if name in metadata.fields}
    if rejected or not parsed or metadata.opening_balance is None:
        if not rejected and not missing and not parsed and metadata.opening_balance == metadata.closing_balance and metadata.printed_total_debits == 0 and metadata.printed_total_credits == 0:
            checks["running_balance_continuity"] = _check("running_balance_continuity", BciCheckStatus.PASS, "no_transactions", fields=balance_fields)
        else:
            checks["running_balance_continuity"] = _check("running_balance_continuity", BciCheckStatus.INSUFFICIENT_DATA, "transaction_candidate_rejected" if rejected else "no_transaction_balance", fields=balance_fields)
    else:
        expected = metadata.opening_balance + parsed[0].signed_amount
        actual = parsed[0].running_balance
        difference = expected - actual
        for prior, current in zip(parsed, parsed[1:]):
            expected = prior.running_balance + current.signed_amount
            actual = current.running_balance
            difference = expected - actual
            if difference != 0:
                break
        checks["running_balance_continuity"] = _check("running_balance_continuity", BciCheckStatus.PASS if difference == 0 else BciCheckStatus.FAIL, "running_balance_matches" if difference == 0 else "running_balance_mismatch", difference, fields=balance_fields)
    if missing:
        summary_difference = None
        checks["summary_balance_equation"] = _check("summary_balance_equation", BciCheckStatus.INSUFFICIENT_DATA, "reconciliation_operand_missing", fields=summary_fields)
    else:
        summary_difference = metadata.opening_balance + metadata.printed_total_credits - metadata.printed_total_debits - metadata.closing_balance
        checks["summary_balance_equation"] = _check("summary_balance_equation", BciCheckStatus.PASS if summary_difference == 0 else BciCheckStatus.FAIL, "summary_matches" if summary_difference == 0 else "summary_mismatch", summary_difference, fields=summary_fields)
    debit_delta = sum((record.debit or Decimal("0") for record in parsed), Decimal("0")) - (metadata.printed_total_debits or Decimal("0"))
    credit_delta = sum((record.credit or Decimal("0") for record in parsed), Decimal("0")) - (metadata.printed_total_credits or Decimal("0"))
    totals_diff = debit_delta if debit_delta != 0 else credit_delta
    checks["parsed_totals_match_printed"] = _check("parsed_totals_match_printed", BciCheckStatus.INSUFFICIENT_DATA if rejected or metadata.printed_total_debits is None or metadata.printed_total_credits is None else (BciCheckStatus.PASS if debit_delta == 0 and credit_delta == 0 else BciCheckStatus.FAIL), "transaction_candidate_rejected" if rejected else "reconciliation_operand_missing" if metadata.printed_total_debits is None or metadata.printed_total_credits is None else ("totals_match" if totals_diff == 0 else "totals_mismatch"), totals_diff if metadata.printed_total_debits is not None and metadata.printed_total_credits is not None else None, fields={name: metadata.fields[name] for name in ("printed_total_debits", "printed_total_credits") if name in metadata.fields})
    if rejected or not parsed or metadata.closing_balance is None:
        checks["final_running_balance_matches"] = _check("final_running_balance_matches", BciCheckStatus.INSUFFICIENT_DATA if rejected or metadata.closing_balance is None else BciCheckStatus.PASS if metadata.opening_balance == metadata.closing_balance else BciCheckStatus.FAIL, "transaction_candidate_rejected" if rejected else "reconciliation_operand_missing" if metadata.closing_balance is None else "final_balance_matches" if metadata.opening_balance == metadata.closing_balance else "final_balance_mismatch", fields=balance_fields)
    else:
        final_difference = parsed[-1].running_balance - metadata.closing_balance
        checks["final_running_balance_matches"] = _check("final_running_balance_matches", BciCheckStatus.PASS if final_difference == 0 else BciCheckStatus.FAIL, "final_balance_matches" if final_difference == 0 else "final_balance_mismatch", final_difference, fields=balance_fields)
    status = BciReconciliationStatus.INSUFFICIENT_DATA if rejected or missing else BciReconciliationStatus.RECONCILED if all(check.status is BciCheckStatus.PASS for check in checks.values()) else BciReconciliationStatus.NOT_RECONCILED
    first_difference = next((check.difference for check in checks.values() if check.difference not in (None, Decimal("0"))), None)
    return BciHistoricalReconciliation(status, checks, operands, missing, first_difference)


def _check(name: str, status: BciCheckStatus, reason: str, difference: Decimal | None = None, *, fields: dict[str, FieldProvenance] | None = None) -> BciHistoricalReconciliationCheck:
    return BciHistoricalReconciliationCheck(name, status, difference, reason, fields=fields or {})


def _ignored(ref: _LineRef, reason: str) -> BciHistoricalSourceRecord:
    token_ordinals = tuple(token.extraction_ordinal for token in ref.tokens)
    fields = {"record": _provenance(ref, reason)} if ref.tokens else {}
    return BciHistoricalSourceRecord(BciRowOutcome.IGNORED, reason, ref.page.ordinal, 0, (ref.line.ordinal,), token_ordinals, fields)


def _date_like_in_band(ref: _LineRef) -> bool:
    return any(_DATE_LIKE_RE.fullmatch(token.text) and _in_band(token, _BANDS["date"]) for token in ref.tokens)


def _row_candidate_start(ref: _LineRef) -> bool:
    if not _inside_table(ref):
        return False
    has_date_band = any(_in_band(token, _BANDS["date"]) for token in ref.tokens)
    has_financial_band = any(
        _in_band(token, _BANDS[name])
        for name in ("debit", "credit", "balance")
        for token in ref.tokens
    )
    has_row_text = any(
        _in_band(token, _BANDS[name])
        for name in ("branch", "description", "reference")
        for token in ref.tokens
    )
    return has_financial_band and (has_date_band or has_row_text)


def _inside_table(ref: _LineRef) -> bool:
    return bool(ref.tokens) and all(
        token.bbox.x0 >= Decimal("40") - _TOLERANCE
        and token.bbox.x1 <= Decimal("606") + _TOLERANCE
        for token in ref.tokens
    )


def _in_band(token: Token, band: tuple[Decimal, Decimal]) -> bool:
    return token.bbox.x0 >= band[0] - _TOLERANCE and token.bbox.x0 < band[1] + _TOLERANCE


def _join_text(tokens: list[Token]) -> str | None:
    value = " ".join(token.text for token in tokens).strip()
    return value or None


def _provenance(ref: _LineRef, role: str) -> FieldProvenance:
    bbox = ref.line.bbox
    return FieldProvenance(ref.page.ordinal, (ref.line.ordinal,), tuple(token.extraction_ordinal for token in ref.tokens), bbox, role, "inside", ref.page.width, ref.page.height, _normalized(bbox, ref.page))


def _provenance_group(group: _RowGroup, role: str) -> FieldProvenance:
    boxes = tuple(ref.line.bbox for ref in group.refs)
    bbox = BoundingBox.union(boxes)
    return FieldProvenance(group.page.ordinal, tuple(ref.line.ordinal for ref in group.refs), tuple(token.extraction_ordinal for ref in group.refs for token in ref.tokens), bbox, role, "inside", group.page.width, group.page.height, _normalized(bbox, group.page))


def _provenance_tokens(page: Page, refs: tuple[_LineRef, ...], tokens: list[Token], role: str) -> FieldProvenance:
    bbox = BoundingBox.union(tuple(token.bbox for token in tokens))
    line_ordinals = tuple(ref.line.ordinal for ref in refs if any(token.extraction_ordinal in ref.line.token_ordinals for token in tokens))
    return FieldProvenance(page.ordinal, line_ordinals, tuple(token.extraction_ordinal for token in tokens), bbox, role, "inside", page.width, page.height, _normalized(bbox, page))


def _normalized(box: BoundingBox, page: Page) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return tuple((value / limit).quantize(Decimal("0.000001")) for value, limit in zip((box.x0, box.y0, box.x1, box.y1), (page.width, page.height, page.width, page.height)))  # type: ignore[return-value]


def _make_date(parts: tuple[str, str, str], code: str) -> date:
    try:
        return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except ValueError:
        raise BciHistoricalParserError(code) from None
