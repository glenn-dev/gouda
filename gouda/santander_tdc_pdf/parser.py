"""Fail-closed Santander TDC v1 recognition and parsing over canonical GIR."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable

from .extraction import (
    GIR_VERSION, PROFILE_VERSION, BoundingBox, Line, Page, TdcPdfGir, Token,
    recognition_key,
)
from .types import (
    AdditionalPageSpan, FieldProvenance, FinancialCategory, ParserStatus,
    ReconciliationEvidence, ReconciliationStatus, RowOutcome, SectionState,
    SourceRecord, StatementMetadata, TdcPdfParserResult,
)


PARSER_VERSION = "santander-tdc-pdf-v1"
SOURCE_VARIANT = "santander_credit_card_pdf"
_EDGE_TOLERANCE = Decimal("3.00")
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?!\d)")
_FLEX_DATE_RE = re.compile(r"\b(\d{1,2})\s*(?:[/.-]\s*|\s+de\s+)(\d{1,2})\s*(?:[/.-]\s*|\s+de\s+)(\d{2,4})\b", re.IGNORECASE)
_SPANISH_DATE_RE = re.compile(r"\b(\d{1,2})\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{2,4})\b", re.IGNORECASE)
_SPANISH_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_MONEY_RE = re.compile(r"^[($-]?[0-9][0-9. ]*(?:,[0-9]{1,2}|\.[0-9]{1,2})?[)]?$")
_CURRENCY = {"clp", "usd", "eur", "ars", "brl", "mxn", "uf"}
_DATE_LABELS = {"fecha", "date", "dia"}
_DETAIL_LABELS = {"detalle", "descripcion", "concepto", "referencia"}
_CURRENCY_LABELS = {"moneda", "currency"}
_SIMPLE_AMOUNT_LABELS = {"monto", "importe", "valor", "amount"}
_ANY_MONETARY_LABELS = _SIMPLE_AMOUNT_LABELS | {"cargo", "total"}
_FINANCIAL_STATES = {
    SectionState.BILLED_DOMESTIC,
    SectionState.BILLED_INTERNATIONAL,
    SectionState.BILLED_INSTALLMENT,
    SectionState.BILLED_OTHER,
    SectionState.PAYMENTS_CREDITS,
    SectionState.FINANCIAL_CHARGES,
    SectionState.UNBILLED,
}
_CURRENT_FINANCIAL_STATES = _FINANCIAL_STATES - {SectionState.UNBILLED}
_OBSERVED_INSTALLMENT_HEADER = (
    "lugar", "de", "fecha", "de", "descripcion", "operacion", "o", "cobro",
    "monto", "monto", "cargo", "del", "mes",
)
_EXPLICIT_INSTALLMENT_HEADER = ("fecha", "detalle", "cuota", "importe", "cargo")
_OBSERVED_HEADER_CONTINUATIONS = (
    ("operacion", "operacion", "origen", "total", "a"),
    ("nocuota", "valor", "cuota"),
    ("operacion", "pagar"),
    ("mensual",),
    ("o", "cobro"),
)


class TdcPdfParserError(Exception):
    """Safe document-fatal parser error; no source values are included."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class UnsupportedTdcPdfError(TdcPdfParserError):
    pass


class ContradictoryTdcPdfError(TdcPdfParserError):
    pass


@dataclass(frozen=True)
class _LineRef:
    index: int
    page: Page
    line: Line
    tokens: tuple[Token, ...]
    key: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class _Heading:
    state: SectionState
    category: FinancialCategory | None
    family: str
    source: _LineRef


@dataclass(frozen=True)
class _Band:
    left: Decimal
    right: Decimal

    def intersects(self, token: Token) -> bool:
        return token.bbox.x1 >= self.left - _EDGE_TOLERANCE and token.bbox.x0 <= self.right + _EDGE_TOLERANCE

    def contains(self, token: Token) -> bool:
        return token.bbox.x0 >= self.left - _EDGE_TOLERANCE and token.bbox.x1 <= self.right + _EDGE_TOLERANCE


@dataclass(frozen=True)
class _HeaderProfile:
    family: str
    name: str
    state: SectionState
    source: _LineRef
    signature: tuple[str, ...]
    source_refs: tuple[_LineRef, ...]
    date_band: _Band
    description_band: _Band
    amount_band: _Band
    currency_band: _Band | None = None
    location_band: _Band | None = None
    reference_band: _Band | None = None
    context_amount_bands: tuple[_Band, ...] = ()
    installment_number_band: _Band | None = None
    installment_amount_band: _Band | None = None


@dataclass(frozen=True)
class _CurrencyContext:
    code: str
    provenance: FieldProvenance


@dataclass
class _OpenGroup:
    refs: list[_LineRef]
    profile: _HeaderProfile
    section: _Heading
    ordinal: int
    authorized_continuation_page: int | None = None


def parse_tdc_pdf_gir(gir: TdcPdfGir) -> TdcPdfParserResult:
    refs = _line_refs(gir)
    _recognize_extraction_boundary(gir)
    metadata, metadata_indexes = _metadata(refs)
    _recognize_document_context(refs, metadata)

    records: list[SourceRecord] = []
    state = SectionState.PREAMBLE
    section: _Heading | None = None
    active_header: _HeaderProfile | None = None
    open_group: _OpenGroup | None = None
    row_ordinal = 0
    saw_billed_header = False
    rejected_billed = False
    summary_refs: list[_LineRef] = []

    def close_group() -> None:
        nonlocal open_group, rejected_billed
        if open_group is None:
            return
        record = _parse_group(open_group, metadata)
        records.append(record)
        if record.outcome is RowOutcome.REJECTED and record.section is not SectionState.UNBILLED:
            rejected_billed = True
        open_group = None

    for position, ref in enumerate(refs):
        next_ref = refs[position + 1] if position + 1 < len(refs) else None
        if open_group is not None and ref.page.ordinal != open_group.refs[-1].page.ordinal and ref.page.ordinal != open_group.authorized_continuation_page:
            early_heading = _heading_for(ref, next_ref, state, open_group.profile)
            try:
                early_header = _header_kind(ref)
            except ContradictoryTdcPdfError:
                early_header = None
            if _group_has_primary_amount(open_group) and early_header is None and not (
                early_heading is not None and _is_repeated_page_heading(early_heading, open_group, next_ref)
            ):
                close_group()
        if ref.index in metadata_indexes:
            records.append(_ignored(ref, state, "metadata"))
            continue

        try:
            raw_header_kind = _header_kind(ref)
        except ContradictoryTdcPdfError:
            if active_header is not None and state in _FINANCIAL_STATES:
                raise ContradictoryTdcPdfError("incompatible_repeated_header") from None
            raise
        if active_header is not None and _is_header_continuation(ref, active_header):
            active_header = replace(active_header, source_refs=active_header.source_refs + (ref,))
            records.append(_ignored(ref, state, "header_continuation"))
            continue
        continuation = open_group is not None and _description_continuation(ref, open_group.profile)
        heading = None if continuation else _heading_for(ref, next_ref, state, active_header)

        if open_group is not None and ref.page.ordinal != open_group.refs[-1].page.ordinal and ref.page.ordinal != open_group.authorized_continuation_page:
            if heading is not None and _is_repeated_page_heading(heading, open_group, next_ref):
                records.append(_ignored(ref, state, "repeated_section_heading"))
                continue
            if raw_header_kind is not None:
                candidate = _build_header(ref, state)
                if not _headers_compatible(open_group.profile, candidate):
                    raise ContradictoryTdcPdfError("incompatible_repeated_header")
                open_group.authorized_continuation_page = ref.page.ordinal
                active_header = candidate
                records.append(_ignored(ref, state, "repeated_header"))
                continue
            raise ContradictoryTdcPdfError("unproven_cross_page_continuation")

        if heading is not None:
            close_group()
            repeated_page_heading = _is_repeated_page_heading(heading, None, next_ref, state=state, active_header=active_header)
            if repeated_page_heading:
                records.append(_ignored(ref, state, "repeated_section_heading"))
                continue
            _validate_transition(state, heading.state)
            state = heading.state
            section = heading
            active_header = None
            row_ordinal = 0
            records.append(_ignored(ref, state, "section_marker"))
            continue

        if raw_header_kind is not None:
            if state not in _FINANCIAL_STATES:
                raise ContradictoryTdcPdfError("financial_header_outside_recognized_state")
            candidate = _build_header(ref, state)
            if active_header is not None and not _headers_compatible(active_header, candidate):
                raise ContradictoryTdcPdfError("incompatible_repeated_header")
            close_group()
            active_header = candidate
            prior_header = any(record.reason_code in ("table_header", "repeated_header") for record in records)
            if state in _CURRENT_FINANCIAL_STATES:
                saw_billed_header = True
            records.append(_ignored(ref, state, "repeated_header" if prior_header else "table_header"))
            continue

        if state not in _FINANCIAL_STATES and _has_date(ref) and _money_tokens(ref.tokens):
            raise ContradictoryTdcPdfError("financial_content_outside_recognized_state")

        date_token = _date_token(ref, active_header)
        if date_token is not None:
            if state not in _FINANCIAL_STATES or section is None:
                raise ContradictoryTdcPdfError("financial_content_outside_recognized_state")
            if active_header is None or active_header.source.page.ordinal != ref.page.ordinal:
                raise ContradictoryTdcPdfError("transaction_header_missing_on_page")
            close_group()
            row_ordinal += 1
            if active_header is None:
                raise ContradictoryTdcPdfError("transaction_header_missing")
            open_group = _OpenGroup([ref], active_header, section, row_ordinal)
            continue

        if open_group is not None and _is_footer_boundary(ref, open_group):
            close_group()
            records.append(_ignored(ref, state, "page_chrome"))
            continue

        if open_group is not None and continuation:
            open_group.refs.append(ref)
            continue

        if _financial_candidate_without_date(ref, active_header):
            if state not in _FINANCIAL_STATES or section is None:
                raise ContradictoryTdcPdfError("financial_content_outside_recognized_state")
            close_group()
            row_ordinal += 1
            if state is SectionState.UNBILLED:
                records.append(_ignored(ref, state, "unbilled_future", row_ordinal))
            else:
                records.append(_rejected(ref, state, row_ordinal, "date_invalid"))
                rejected_billed = True
            continue

        if open_group is not None:
            raise ContradictoryTdcPdfError("unknown_heading_interrupts_financial_structure")

        if state in _CURRENT_FINANCIAL_STATES:
            if _recognized_summary(ref, active_header):
                records.append(_ignored(ref, state, "summary_total"))
                continue
            if _is_stable_page_chrome(ref, active_header):
                records.append(_ignored(ref, state, "page_chrome"))
                continue
            raise ContradictoryTdcPdfError("unknown_heading_interrupts_financial_structure")
        if state is SectionState.UNBILLED:
            records.append(_ignored(ref, state, "unbilled_future"))
            continue
        if state in (SectionState.PREAMBLE, SectionState.STATEMENT_SUMMARY):
            summary_refs.append(ref)
            if state is SectionState.PREAMBLE and _is_summary_context(ref):
                state = SectionState.STATEMENT_SUMMARY
            records.append(_ignored(ref, state, "summary_structure"))
            continue
        records.append(_ignored(ref, state, "footer_legal"))

    close_group()
    if not saw_billed_header:
        raise UnsupportedTdcPdfError("billed_section_not_found")
    reconciliation = _reconcile(summary_refs, metadata, rejected_billed)
    return TdcPdfParserResult(
        ParserStatus.RECOGNIZED, "Santander", "credit_card", SOURCE_VARIANT,
        PARSER_VERSION, metadata, tuple(records), reconciliation,
        gir_version=gir.gir_version,
        extraction_profile_version=gir.profile_version,
    )


def parse_tdc_pdf(source) -> TdcPdfParserResult:
    """Compose the existing extraction adapter with the GIR-only parser."""
    from .extraction import extract_tdc_pdf
    return parse_tdc_pdf_gir(extract_tdc_pdf(source))


def _recognize_extraction_boundary(gir: TdcPdfGir) -> None:
    if gir.gir_version != GIR_VERSION or gir.profile_version != PROFILE_VERSION:
        raise UnsupportedTdcPdfError("unsupported_gir_profile")


def _line_refs(gir: TdcPdfGir) -> list[_LineRef]:
    refs = []
    index = 0
    for page in gir.pages:
        token_map = {token.extraction_ordinal: token for token in page.tokens}
        for line in page.lines:
            index += 1
            tokens = tuple(token_map[ordinal] for ordinal in line.token_ordinals)
            refs.append(_LineRef(index, page, line, tokens, recognition_key(" ".join(token.text for token in tokens)), tuple(_label(token.text) for token in tokens)))
    return refs


def _label(value: str) -> str:
    return re.sub(r"(^[^\w]+|[^\w]+$)", "", recognition_key(value))


def _heading_labels(ref: _LineRef) -> tuple[str, ...]:
    labels = list(ref.labels)
    if labels:
        labels[0] = re.sub(r"^\d+[.)-]?", "", labels[0])
        if re.fullmatch(r"[ivxlcdm]+[.)-]?", labels[0]):
            labels[0] = ""
    return tuple(label for label in labels if label)


def _recognize_document_context(refs: list[_LineRef], metadata: StatementMetadata) -> None:
    found_header = False
    first_header_error = None
    for ref in refs:
        try:
            found_header |= _header_kind(ref) is not None
        except ContradictoryTdcPdfError as error:
            first_header_error = first_header_error or error
    if not found_header:
        if first_header_error is not None:
            raise first_header_error
        raise UnsupportedTdcPdfError("transaction_header_missing")
    if metadata.card_product_context != "credit_card":
        raise UnsupportedTdcPdfError("provider_product_context_missing")
    if not any(("estado" in ref.labels and "cuenta" in ref.labels) or "resumen" in ref.labels or "periodo" in ref.labels for ref in refs):
        raise UnsupportedTdcPdfError("statement_context_missing")


def _metadata(refs: list[_LineRef]) -> tuple[StatementMetadata, set[int]]:
    indexes: set[int] = set()
    product_refs: list[_LineRef] = []
    for ref in refs:
        if _line_contains(ref, "santander") and _line_contains(ref, "tarjeta") and _line_contains(ref, "credito"):
            product_refs = [ref]
            break
    if not product_refs:
        for ref in refs:
            if not _line_contains(ref, "santander"):
                continue
            nearby = [
                other for other in refs
                if other.page.ordinal == ref.page.ordinal
                and abs(other.line.ordinal - ref.line.ordinal) <= 12
                and (
                    ref.line.bbox.y1 <= ref.page.height * Decimal("0.20")
                    or ref.line.bbox.y0 >= ref.page.height * Decimal("0.50")
                )
            ]
            product = next((other for other in nearby if _line_contains(other, "tarjeta") and _line_contains(other, "credito")), None)
            if product is not None:
                product_refs = [ref, product]
                break
    if not product_refs:
        raise UnsupportedTdcPdfError("provider_product_context_missing")
    if not any("corte" in ref.labels or "facturacion" in ref.labels for ref in refs):
        raise UnsupportedTdcPdfError("cutoff_metadata_missing")

    period_candidates = []
    for ref in refs:
        dates = _dates_in_ref(ref)
        if "periodo" in ref.labels and "anterior" not in ref.labels and len(dates) == 2:
            period_candidates.append((ref, dates))
    if not period_candidates:
        raise UnsupportedTdcPdfError("statement_period_missing")
    preferred = [candidate for candidate in period_candidates if "facturacion" in candidate[0].labels]
    period_ref, period_dates = (preferred or period_candidates)[0]
    period_start, period_end = sorted(period_dates)

    cutoff_ref = None
    cutoff_date = None
    for ref in refs:
        if "corte" in ref.labels:
            values = _dates_in_ref(ref) or _nearby_dates(refs, ref.index)
            if len(values) == 1:
                cutoff_ref, cutoff_date = ref, values[0]
                break
    if cutoff_date is None and "facturacion" in period_ref.labels:
        cutoff_ref, cutoff_date = period_ref, period_end
    if cutoff_date is None:
        raise UnsupportedTdcPdfError("cutoff_date_ambiguous")

    due_label_ref = next((ref for ref in refs if "vencimiento" in ref.labels), None)
    if due_label_ref is None:
        raise UnsupportedTdcPdfError("due_date_metadata_missing")
    due_values = _dates_in_ref(due_label_ref)
    due_value_ref = due_label_ref
    if not due_values:
        nearby = _nearby_date_refs(refs, due_label_ref.index)
        if len(nearby) == 1:
            due_value_ref, due_values = nearby[0]
    if len(due_values) != 1:
        raise UnsupportedTdcPdfError("due_date_ambiguous")

    currency_contexts: list[_CurrencyContext] = []
    currency_ref: _LineRef | None = None
    for ref in refs:
        if "moneda" not in ref.labels:
            continue
        explicit = [label.upper() for label in ref.labels if label in _CURRENCY - {"uf"}]
        if explicit:
            currency_contexts.append(_CurrencyContext(explicit[0], _provenance_refs((ref,), "statement_currency")))
            currency_ref = ref
        elif "nacional" in ref.labels and "tarjeta" in ref.labels and "credito" in ref.labels:
            currency_contexts.append(_CurrencyContext("CLP", _provenance_refs((ref,), "statement_currency")))
            currency_ref = ref
    codes = {context.code for context in currency_contexts}
    if len(codes) > 1:
        raise UnsupportedTdcPdfError("statement_currency_ambiguous")
    currency = currency_contexts[0] if currency_contexts else None

    fields = {
        "statement_period": _provenance_refs((period_ref,), "statement_period"),
        "billing_cutoff_date": _provenance_refs((cutoff_ref,), "billing_cutoff_date"),
        "payment_due_date": _provenance_refs(tuple(dict.fromkeys((due_label_ref, due_value_ref))), "payment_due_date"),
        "card_product_context": _provenance_refs(tuple(product_refs), "card_product_context"),
    }
    if currency is not None:
        fields["statement_currency"] = currency.provenance
    for ref in product_refs + [period_ref, cutoff_ref, due_label_ref, due_value_ref]:
        indexes.add(ref.index)
    if currency_ref is not None:
        indexes.add(currency_ref.index)
    for ref in refs:
        labels = set(ref.labels)
        if (
            ("santander" in labels and ("tarjeta" in labels or "tarjetas" in labels) and "credito" in labels)
            or ("periodo" in labels and len(_dates_in_ref(ref)) == 2)
            or "corte" in labels
            or "vencimiento" in labels
            or ("moneda" in labels and (bool(labels & (_CURRENCY - {"uf"})) or {"nacional", "tarjeta", "credito"} <= labels))
        ):
            indexes.add(ref.index)
    return StatementMetadata(period_start, period_end, cutoff_date, due_values[0], "credit_card", currency.code if currency else None, fields), indexes


def _nearby_date_refs(refs: list[_LineRef], index: int) -> list[tuple[_LineRef, list[date]]]:
    origin = refs[index - 1]
    found = []
    for distance in (1, 2, 3):
        for candidate_index in (index - 1 - distance, index - 1 + distance):
            if 0 <= candidate_index < len(refs):
                ref = refs[candidate_index]
                if ref.page.ordinal != origin.page.ordinal:
                    continue
                values = _dates_in_ref(ref)
                if values:
                    found.append((ref, values))
        if found:
            break
    return found


def _nearby_dates(refs: list[_LineRef], index: int) -> list[date]:
    return [value for _, values in _nearby_date_refs(refs, index) for value in values]


def _dates_in_ref(ref: _LineRef) -> list[date]:
    text = " ".join(token.text for token in ref.tokens)
    result: list[date] = []
    seen: set[date] = set()
    numeric_spans = []
    for match in _DATE_RE.finditer(text):
        numeric_spans.append(match.span())
        day, month, year = match.groups()
        if year is None:
            continue
        year_number = int(year) + 2000 if len(year) == 2 else int(year)
        try:
            value = date(year_number, int(month), int(day))
        except ValueError:
            continue
        if value not in seen:
            result.append(value)
            seen.add(value)
    for match in _FLEX_DATE_RE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in numeric_spans):
            continue
        day, month, year = map(int, match.groups())
        if year < 100:
            year += 2000
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if value not in seen:
            result.append(value)
            seen.add(value)
    for match in _SPANISH_DATE_RE.finditer(text):
        day, month, year = match.groups()
        year_number = int(year) + 2000 if len(year) == 2 else int(year)
        try:
            value = date(year_number, _SPANISH_MONTHS[month.casefold()], int(day))
        except ValueError:
            continue
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _header_kind(ref: _LineRef) -> str | None:
    labels = ref.labels
    if labels == _OBSERVED_INSTALLMENT_HEADER:
        return "observed_installment"
    if labels == _EXPLICIT_INSTALLMENT_HEADER:
        return "explicit_installment"
    date_indexes = [index for index, label in enumerate(labels) if label in _DATE_LABELS]
    detail_indexes = [index for index, label in enumerate(labels) if label in _DETAIL_LABELS]
    monetary_indexes = [index for index, label in enumerate(labels) if label in _ANY_MONETARY_LABELS]
    if not (date_indexes and detail_indexes and monetary_indexes):
        return None
    currency_indexes = [index for index, label in enumerate(labels) if label in _CURRENCY_LABELS]
    if len(date_indexes) != 1 or len(detail_indexes) != 1 or len(monetary_indexes) != 1 or len(currency_indexes) > 1:
        raise ContradictoryTdcPdfError("unsupported_column_order")
    amount_index = monetary_indexes[0]
    if labels[amount_index] not in _SIMPLE_AMOUNT_LABELS:
        raise ContradictoryTdcPdfError("unsupported_column_order")
    order = [date_indexes[0], detail_indexes[0], *(currency_indexes or []), amount_index]
    if order != sorted(order):
        raise ContradictoryTdcPdfError("unsupported_column_order")
    return "standard"


def _build_header(ref: _LineRef, state: SectionState) -> _HeaderProfile:
    kind = _header_kind(ref)
    if kind is None:
        raise ContradictoryTdcPdfError("unsupported_financial_table_geometry")
    if kind in ("observed_installment", "explicit_installment") and state is not SectionState.BILLED_INSTALLMENT:
        raise ContradictoryTdcPdfError("header_profile_state_mismatch")
    if kind == "observed_installment":
        date_token, detail_token = ref.tokens[2], ref.tokens[4]
        context_one, context_two, amount_token = ref.tokens[8], ref.tokens[9], ref.tokens[10]
        date_band = _between_band(ref.page, date_token, detail_token, left_edge=date_token.bbox.x0 - _EDGE_TOLERANCE)
        description_band = _between_band(ref.page, detail_token, context_one)
        split_one = _midpoint(context_one.bbox.x1, context_two.bbox.x0)
        split_two = _midpoint(context_two.bbox.x1, amount_token.bbox.x0)
        location_right = _midpoint(ref.tokens[0].bbox.x1, date_token.bbox.x0)
        return _HeaderProfile(kind, "installment_billed", state, ref, ref.labels, (ref,), date_band, description_band, _Band(split_two, ref.page.width), location_band=_Band(Decimal("0"), location_right), reference_band=_Band(description_band.right, context_one.bbox.x0 - _EDGE_TOLERANCE), context_amount_bands=(_Band(description_band.right, split_one), _Band(split_one, split_two)))
    if kind == "explicit_installment":
        date_token, detail_token, installment_token, installment_amount_token, amount_token = ref.tokens
        date_band = _between_band(ref.page, date_token, detail_token, left_edge=date_token.bbox.x0 - _EDGE_TOLERANCE)
        description_band = _between_band(ref.page, detail_token, installment_token)
        split_one = _midpoint(installment_token.bbox.x1, installment_amount_token.bbox.x0)
        split_two = _midpoint(installment_amount_token.bbox.x1, amount_token.bbox.x0)
        return _HeaderProfile(kind, "installment_billed", state, ref, ref.labels, (ref,), date_band, description_band, _Band(split_two, ref.page.width), installment_number_band=_Band(description_band.right, split_one), installment_amount_band=_Band(split_one, split_two))
    date_token = next(token for token, label in zip(ref.tokens, ref.labels) if label in _DATE_LABELS)
    detail_token = next(token for token, label in zip(ref.tokens, ref.labels) if label in _DETAIL_LABELS)
    amount_token = next(token for token, label in zip(ref.tokens, ref.labels) if label in _SIMPLE_AMOUNT_LABELS)
    currency_token = next((token for token, label in zip(ref.tokens, ref.labels) if label in _CURRENCY_LABELS), None)
    date_band = _between_band(ref.page, date_token, detail_token, left_edge=date_token.bbox.x0 - _EDGE_TOLERANCE)
    next_token = currency_token or amount_token
    description_band = _between_band(ref.page, detail_token, next_token)
    currency_band = None
    if currency_token is not None:
        currency_band = _Band(description_band.right, _midpoint(currency_token.bbox.x1, amount_token.bbox.x0))
        amount_left = currency_band.right
    else:
        amount_left = description_band.right
    return _HeaderProfile(kind, _profile_name(state), state, ref, ref.labels, (ref,), date_band, description_band, _Band(amount_left, ref.page.width), currency_band)


def _between_band(page: Page, current: Token, following: Token, *, left_edge: Decimal | None = None) -> _Band:
    left = left_edge if left_edge is not None else current.bbox.x0 - _EDGE_TOLERANCE
    return _Band(max(Decimal("0"), left), min(page.width, _midpoint(current.bbox.x1, following.bbox.x0)))


def _midpoint(left: Decimal, right: Decimal) -> Decimal:
    return (left + right) / 2


def _profile_name(state: SectionState) -> str:
    return {
        SectionState.BILLED_DOMESTIC: "domestic_billed",
        SectionState.BILLED_INTERNATIONAL: "international_billed",
        SectionState.BILLED_INSTALLMENT: "installment_billed",
        SectionState.BILLED_OTHER: "other_billed",
        SectionState.PAYMENTS_CREDITS: "payments_credits",
        SectionState.FINANCIAL_CHARGES: "financial_charges",
        SectionState.UNBILLED: "unbilled_future",
    }[state]


def _headers_compatible(first: _HeaderProfile, second: _HeaderProfile) -> bool:
    if first.family != second.family or first.signature != second.signature or first.state != second.state:
        return False
    return all(abs(a.bbox.x0 - b.bbox.x0) <= _EDGE_TOLERANCE and abs(a.bbox.x1 - b.bbox.x1) <= _EDGE_TOLERANCE for a, b in zip(first.source.tokens, second.source.tokens))


def _is_header_continuation(ref: _LineRef, profile: _HeaderProfile) -> bool:
    if profile.family != "observed_installment" or ref.page.ordinal != profile.source.page.ordinal:
        return False
    offset = ref.line.ordinal - profile.source.line.ordinal
    if not (1 <= offset <= len(_OBSERVED_HEADER_CONTINUATIONS)) or ref.labels != _OBSERVED_HEADER_CONTINUATIONS[offset - 1]:
        return False
    anchors = profile.source.tokens
    if offset == 1:
        return all(abs(token.bbox.x0 - anchors[index].bbox.x0) <= _EDGE_TOLERANCE for token, index in zip(ref.tokens[:4], (0, 2, 8, 9)))
    if offset == 2:
        return all(profile.amount_band.intersects(token) for token in ref.tokens) and all(first.bbox.x0 < second.bbox.x0 for first, second in zip(ref.tokens, ref.tokens[1:]))
    if offset == 3:
        return all(abs(token.bbox.x0 - anchors[index].bbox.x0) <= _EDGE_TOLERANCE for token, index in zip(ref.tokens, (8, 9)))
    if offset == 4:
        return profile.amount_band.intersects(ref.tokens[0])
    return abs(ref.tokens[0].bbox.x0 - anchors[8].bbox.x0) <= _EDGE_TOLERANCE and ref.tokens[1].bbox.x0 > ref.tokens[0].bbox.x0


def _heading_for(ref: _LineRef, next_ref: _LineRef | None, current_state: SectionState | None = None, active_header: _HeaderProfile | None = None) -> _Heading | None:
    labels = _heading_labels(ref)
    if _has_date(ref) or _money_tokens(ref.tokens):
        return None
    if active_header is not None and current_state in _FINANCIAL_STATES and ref.tokens:
        first = ref.tokens[0]
        if active_header.description_band.contains(first) or (
            active_header.reference_band is not None and active_header.reference_band.contains(first)
        ):
            return None
    exact: dict[tuple[str, ...], tuple[SectionState, FinancialCategory | None, str]] = {
        ("compras", "nacionales"): (SectionState.BILLED_DOMESTIC, FinancialCategory.PURCHASE_CHARGE, "domestic_billed"),
        ("compras", "nacional"): (SectionState.BILLED_DOMESTIC, FinancialCategory.PURCHASE_CHARGE, "domestic_billed"),
        ("compras",): (SectionState.BILLED_DOMESTIC, FinancialCategory.PURCHASE_CHARGE, "domestic_billed"),
        ("cargos",): (SectionState.BILLED_OTHER, FinancialCategory.PURCHASE_CHARGE, "other_billed"),
        ("movimientos",): (SectionState.BILLED_OTHER, FinancialCategory.PURCHASE_CHARGE, "other_billed"),
        ("compras", "internacionales"): (SectionState.BILLED_INTERNATIONAL, FinancialCategory.PURCHASE_CHARGE, "international_billed"),
        ("compras", "internacional"): (SectionState.BILLED_INTERNATIONAL, FinancialCategory.PURCHASE_CHARGE, "international_billed"),
        ("compras", "en", "cuotas"): (SectionState.BILLED_INSTALLMENT, FinancialCategory.PURCHASE_CHARGE, "installment_billed"),
        ("pagos",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.PAYMENT, "payments"),
        ("abonos",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.PAYMENT, "payments"),
        ("creditos",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.CREDIT_REFUND, "credits"),
        ("credito",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.CREDIT_REFUND, "credits"),
        ("devoluciones",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.CREDIT_REFUND, "credits"),
        ("reintegros",): (SectionState.PAYMENTS_CREDITS, FinancialCategory.CREDIT_REFUND, "credits"),
        ("intereses",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.INTEREST, "interest"),
        ("interes",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.INTEREST, "interest"),
        ("comisiones",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.COMMISSION, "commission"),
        ("comision",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.COMMISSION, "commission"),
        ("impuestos",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.TAX, "tax"),
        ("impuesto",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.TAX, "tax"),
        ("seguros",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.INSURANCE, "insurance"),
        ("seguro",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.INSURANCE, "insurance"),
        ("avances",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.CASH_ADVANCE, "cash_advance"),
        ("avance",): (SectionState.FINANCIAL_CHARGES, FinancialCategory.CASH_ADVANCE, "cash_advance"),
        ("no", "facturado"): (SectionState.UNBILLED, None, "unbilled"),
        ("no", "facturada"): (SectionState.UNBILLED, None, "unbilled"),
        ("no", "facturados"): (SectionState.UNBILLED, None, "unbilled"),
        ("proximos", "movimientos"): (SectionState.UNBILLED, None, "unbilled"),
        ("mensajes",): (SectionState.FOOTER_LEGAL, None, "footer"),
        ("informacion", "legal"): (SectionState.FOOTER_LEGAL, None, "footer"),
        ("contacto",): (SectionState.FOOTER_LEGAL, None, "footer"),
    }
    if labels in exact:
        state, category, family = exact[labels]
        return _Heading(state, category, family, ref)
    if labels == ("informacion", "de", "pago") and current_state in _FINANCIAL_STATES:
        return _Heading(SectionState.FOOTER_LEGAL, None, "payment_information", ref)
    if labels == ("periodo", "actual") and next_ref is not None and _header_kind(next_ref) == "observed_installment":
        return _Heading(SectionState.BILLED_INSTALLMENT, FinancialCategory.PURCHASE_CHARGE, "installment_billed", ref)
    return None


def _validate_transition(current: SectionState, target: SectionState) -> None:
    allowed = {
        SectionState.PREAMBLE: {SectionState.STATEMENT_SUMMARY, SectionState.BILLED_DOMESTIC, SectionState.BILLED_INTERNATIONAL, SectionState.BILLED_INSTALLMENT, SectionState.BILLED_OTHER},
        SectionState.STATEMENT_SUMMARY: {SectionState.BILLED_DOMESTIC, SectionState.BILLED_INTERNATIONAL, SectionState.BILLED_INSTALLMENT, SectionState.BILLED_OTHER},
        SectionState.BILLED_DOMESTIC: {SectionState.BILLED_DOMESTIC, SectionState.BILLED_INTERNATIONAL, SectionState.BILLED_INSTALLMENT, SectionState.BILLED_OTHER, SectionState.PAYMENTS_CREDITS, SectionState.FINANCIAL_CHARGES, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.BILLED_INTERNATIONAL: {SectionState.BILLED_INTERNATIONAL, SectionState.BILLED_INSTALLMENT, SectionState.BILLED_OTHER, SectionState.PAYMENTS_CREDITS, SectionState.FINANCIAL_CHARGES, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.BILLED_INSTALLMENT: {SectionState.BILLED_INSTALLMENT, SectionState.BILLED_OTHER, SectionState.PAYMENTS_CREDITS, SectionState.FINANCIAL_CHARGES, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.BILLED_OTHER: {SectionState.BILLED_OTHER, SectionState.PAYMENTS_CREDITS, SectionState.FINANCIAL_CHARGES, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.PAYMENTS_CREDITS: {SectionState.PAYMENTS_CREDITS, SectionState.FINANCIAL_CHARGES, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.FINANCIAL_CHARGES: {SectionState.FINANCIAL_CHARGES, SectionState.PAYMENTS_CREDITS, SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.UNBILLED: {SectionState.UNBILLED, SectionState.FOOTER_LEGAL},
        SectionState.FOOTER_LEGAL: {SectionState.FOOTER_LEGAL, SectionState.END},
        SectionState.END: set(),
    }
    if target not in allowed[current]:
        raise ContradictoryTdcPdfError("contradictory_section_transition")


def _is_repeated_page_heading(heading: _Heading, group: _OpenGroup | None, next_ref: _LineRef | None, *, state: SectionState | None = None, active_header: _HeaderProfile | None = None) -> bool:
    current_state = group.section.state if group is not None else state
    profile = group.profile if group is not None else active_header
    prior_page = group.refs[-1].page.ordinal if group is not None else profile.source.page.ordinal if profile is not None else None
    if heading.state is not current_state or profile is None or next_ref is None or heading.source.page.ordinal == prior_page or _header_kind(next_ref) is None:
        return False
    return _headers_compatible(profile, _build_header(next_ref, current_state))


def _date_token(ref: _LineRef, header: _HeaderProfile | None) -> Token | None:
    if header is None:
        return None
    return next((token for token in ref.tokens if _DATE_RE.search(token.text) and header.date_band.intersects(token)), None)


def _description_continuation(ref: _LineRef, header: _HeaderProfile) -> bool:
    if _has_date(ref) or _money_tokens(ref.tokens) or _header_kind(ref) is not None:
        return False
    compatible_bands = (header.description_band,)
    if header.location_band is not None:
        compatible_bands += (header.location_band,)
    if header.reference_band is not None:
        compatible_bands += (header.reference_band,)
    return bool(ref.tokens) and all(any(band.contains(token) for band in compatible_bands) for token in ref.tokens)


def _financial_candidate_without_date(ref: _LineRef, header: _HeaderProfile | None) -> bool:
    if header is None or _has_date(ref):
        return False
    monetary = _money_tokens(ref.tokens)
    if not monetary:
        return False
    first_non_monetary = next((token for token in ref.tokens if token not in monetary and _label(token.text) not in _CURRENCY), None)
    if first_non_monetary is None or not header.description_band.contains(first_non_monetary):
        return False
    bands = (header.amount_band,) + header.context_amount_bands
    if header.installment_amount_band is not None:
        bands += (header.installment_amount_band,)
    return any(any(band.intersects(token) for band in bands) for token in monetary)


def _group_has_primary_amount(group: _OpenGroup) -> bool:
    return any(group.profile.amount_band.intersects(token) for ref in group.refs for token in _money_tokens(ref.tokens))


def _parse_group(group: _OpenGroup, metadata: StatementMetadata) -> SourceRecord:
    refs = tuple(group.refs)
    fields = {"row": _provenance_refs(refs, "row")}
    if group.section.state is SectionState.UNBILLED:
        return _group_record(RowOutcome.IGNORED, "unbilled_future", group, fields)
    date_evidence = [(ref, token) for ref in refs for token in ref.tokens if _DATE_RE.search(token.text) and group.profile.date_band.intersects(token)]
    if len(date_evidence) != 1:
        return _group_record(RowOutcome.REJECTED, "date_invalid", group, fields)
    date_ref, date_token = date_evidence[0]
    transaction_date = _parse_row_date(_DATE_RE.search(date_token.text).group(0), metadata)
    if transaction_date is None:
        return _group_record(RowOutcome.REJECTED, "date_invalid", group, fields)

    all_money = [
        (ref, token) for ref in refs for token in _money_tokens(ref.tokens)
        if token is not date_token and not _numeric_location_or_reference(token, group.profile)
    ]
    primary = [(ref, token) for ref, token in all_money if group.profile.amount_band.intersects(token)]
    if len(primary) != 1:
        return _group_record(RowOutcome.REJECTED, "amount_ambiguous" if primary else "amount_malformed", group, fields)
    amount_ref, amount_token = primary[0]
    amount = _parse_money(amount_token.text)
    if amount is None:
        return _group_record(RowOutcome.REJECTED, "amount_malformed", group, fields)
    if amount <= 0:
        return _group_record(RowOutcome.REJECTED, "zero_amount_unsupported", group, fields)

    allowed_context = []
    for band in group.profile.context_amount_bands:
        members = [(ref, token) for ref, token in all_money if band.intersects(token)]
        if len(members) > 1:
            return _group_record(RowOutcome.REJECTED, "amount_ambiguous", group, fields)
        allowed_context.extend(members)
    installment_amount_evidence = []
    if group.profile.installment_amount_band is not None:
        installment_amount_evidence = [(ref, token) for ref, token in all_money if group.profile.installment_amount_band.intersects(token)]
        if len(installment_amount_evidence) > 1:
            return _group_record(RowOutcome.REJECTED, "amount_ambiguous", group, fields)
    installment_number_evidence = []
    if group.profile.installment_number_band is not None:
        installment_number_evidence = [(ref, token) for ref, token in all_money if token.text.isdigit() and group.profile.installment_number_band.intersects(token)]
        if len(installment_number_evidence) > 1:
            return _group_record(RowOutcome.REJECTED, "unsupported_row_geometry", group, fields)
    assigned_tokens = {id(token) for _, token in primary + allowed_context + installment_amount_evidence + installment_number_evidence}
    if any(id(token) not in assigned_tokens for _, token in all_money):
        return _group_record(RowOutcome.REJECTED, "incompatible_monetary_columns", group, fields)

    currency_evidence = []
    if group.profile.currency_band is not None:
        currency_evidence = [(ref, token) for ref in refs for token in ref.tokens if _label(token.text) in _CURRENCY and group.profile.currency_band.intersects(token)]
    if len(currency_evidence) > 1:
        return _group_record(RowOutcome.REJECTED, "currency_ambiguous", group, fields)
    if currency_evidence:
        currency = _label(currency_evidence[0][1].text).upper()
        currency_provenance = _provenance_items(currency_evidence, "billed_currency")
    elif metadata.statement_currency is not None and "statement_currency" in metadata.fields:
        currency = metadata.statement_currency
        currency_provenance = _with_role(metadata.fields["statement_currency"], "billed_currency", "inherited_statement_context")
    else:
        return _group_record(RowOutcome.REJECTED, "currency_ambiguous", group, fields)

    category = group.section.category
    if category is None:
        return _group_record(RowOutcome.REJECTED, "category_ambiguous", group, fields)
    fields["transaction_date"] = _provenance_items(((date_ref, date_token),), "transaction_date")
    fields["billed_amount"] = _provenance_items(((amount_ref, amount_token),), "billed_amount")
    fields["billed_currency"] = currency_provenance
    fields["section_category"] = _provenance_refs((group.section.source,), "section_category")
    fields["header_profile"] = _provenance_refs(group.profile.source_refs, "header_profile")
    description_evidence = [(ref, token) for ref in refs for token in ref.tokens if group.profile.description_band.contains(token) and not _DATE_RE.search(token.text) and not _MONEY_RE.match(token.text.replace("$", ""))]
    description = " ".join(token.text for _, token in description_evidence) or None
    fields["description_detail"] = _provenance_items(description_evidence, "description_detail") if description_evidence else _provenance_refs(refs, "description_detail", "empty_role_band")
    location_evidence = []
    if group.profile.location_band is not None:
        location_evidence = [(ref, token) for ref in refs for token in ref.tokens if group.profile.location_band.contains(token) and not _DATE_RE.search(token.text) and (token.text.isdigit() or not _MONEY_RE.match(token.text.replace("$", "")))]
    location = " ".join(token.text for _, token in location_evidence) or None
    if location_evidence:
        fields["location"] = _provenance_items(location_evidence, "location")
    reference_evidence = []
    if group.profile.reference_band is not None:
        reference_evidence = [(ref, token) for ref in refs for token in ref.tokens if group.profile.reference_band.contains(token) and not _DATE_RE.search(token.text) and (token.text.isdigit() or not _MONEY_RE.match(token.text.replace("$", "")))]
    reference = " ".join(token.text for _, token in reference_evidence) or None
    if reference_evidence:
        fields["reference_authorization"] = _provenance_items(reference_evidence, "reference_authorization")

    installment_number = None
    if len(installment_number_evidence) == 1:
        installment_number = int(installment_number_evidence[0][1].text)
        fields["installment_number"] = _provenance_items(installment_number_evidence, "installment_number")
    installment_amount = None
    if len(installment_amount_evidence) == 1:
        installment_amount = _parse_money(installment_amount_evidence[0][1].text)
        if installment_amount is not None:
            fields["installment_amount"] = _provenance_items(installment_amount_evidence, "installment_amount")
    debt = -amount if category in (FinancialCategory.PAYMENT, FinancialCategory.CREDIT_REFUND) else amount
    return _group_record(RowOutcome.PARSED, "parsed", group, fields, transaction_date=transaction_date, description_detail=description, location=location, reference_authorization=reference, billed_currency=currency, billed_amount=amount, section_category=category, debt_effect=debt, installment_number=installment_number, installment_amount=installment_amount, header_profile=group.profile.name)


def _group_record(outcome: RowOutcome, reason: str, group: _OpenGroup, fields: dict[str, FieldProvenance], **values) -> SourceRecord:
    first = group.refs[0]
    first_page_refs = [ref for ref in group.refs if ref.page.ordinal == first.page.ordinal]
    return SourceRecord(outcome, reason, first.page.ordinal, group.section.state, group.ordinal, tuple(ref.line.ordinal for ref in first_page_refs), tuple(token.extraction_ordinal for ref in first_page_refs for token in ref.tokens), fields, **values)


def _parse_row_date(value: str, metadata: StatementMetadata) -> date | None:
    match = _DATE_RE.fullmatch(value)
    if not match:
        return None
    day, month, year = match.groups()
    if year is not None:
        year_number = int(year) + 2000 if len(year) == 2 else int(year)
        try:
            return date(year_number, int(month), int(day))
        except ValueError:
            return None
    candidates = []
    for year_number in dict.fromkeys((metadata.statement_period_start.year, metadata.statement_period_end.year)):
        try:
            candidate = date(year_number, int(month), int(day))
        except ValueError:
            continue
        if metadata.statement_period_start <= candidate <= metadata.statement_period_end:
            candidates.append(candidate)
    return candidates[0] if len(candidates) == 1 else None


def _parse_money(value: str) -> Decimal | None:
    value = value.strip().replace("$", "").replace(" ", "")
    negative = value.startswith("-") or (value.startswith("(") and value.endswith(")"))
    value = value.strip("()-")
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return -parsed if negative else parsed


def _money_tokens(tokens: Iterable[Token]) -> list[Token]:
    return [token for token in tokens if _MONEY_RE.match(token.text.replace("$", ""))]


def _numeric_location_or_reference(token: Token, profile: _HeaderProfile) -> bool:
    if not token.text.isdigit():
        return False
    return bool(
        (profile.location_band is not None and profile.location_band.contains(token))
        or (profile.reference_band is not None and profile.reference_band.contains(token))
    )


def _line_contains(ref: _LineRef, value: str) -> bool:
    return any(value in label for label in ref.labels)


def _has_date(ref: _LineRef) -> bool:
    return any(_DATE_RE.search(token.text) for token in ref.tokens)


def _recognized_summary(ref: _LineRef, header: _HeaderProfile | None) -> bool:
    if header is None or _has_date(ref):
        return False
    explicit = {
        ("saldo", "anterior"), ("saldo", "actual"), ("saldo", "facturado"),
        ("total", "compras"), ("total", "cargos"), ("total", "pagos"),
        ("total", "intereses"), ("total", "comisiones"), ("total", "impuestos"),
        ("total", "seguros"),
    }
    return _labels_without_values(ref) in explicit and not header.description_band.contains(ref.tokens[0])


def _is_summary_context(ref: _LineRef) -> bool:
    labels = set(ref.labels)
    return ("estado" in labels and "cuenta" in labels) or "resumen" in labels or "periodo" in labels or "vencimiento" in labels


def _is_stable_page_chrome(ref: _LineRef, active_header: _HeaderProfile | None = None) -> bool:
    if ref.line.bbox.y0 >= ref.page.height * Decimal("0.80"):
        return True
    if ref.line.bbox.y0 <= ref.page.height * Decimal("0.15"):
        if active_header is not None and ref.page.ordinal > active_header.source.page.ordinal and not _has_date(ref):
            return True
        return bool(set(ref.labels) & {"santander", "tarjeta", "credito", "pagina"})
    return False


def _is_footer_boundary(ref: _LineRef, group: _OpenGroup) -> bool:
    prior = group.refs[-1]
    return (
        ref.page.ordinal == prior.page.ordinal
        and ref.line.bbox.y0 >= ref.page.height * Decimal("0.75")
        and ref.line.bbox.y0 - prior.line.bbox.y1 > Decimal("24.00")
    )


def _reconcile(summary_refs: list[_LineRef], metadata: StatementMetadata, rejected: bool) -> ReconciliationEvidence:
    label_families = {
        "previous_balance": (("saldo", "anterior"), ("deuda", "anterior"), ("balance", "anterior")),
        "current_billed_balance": (("saldo", "actual"), ("saldo", "facturado"), ("deuda", "actual"), ("total", "a", "pagar")),
        "purchases_charges": (("total", "compras"), ("total", "cargos")),
        "payments_credits": (("total", "pagos"), ("total", "abonos"), ("total", "creditos")),
        "financial_charges": (("total", "intereses"), ("total", "comisiones"), ("total", "impuestos"), ("total", "seguros")),
    }
    operands: dict[str, Decimal] = {}
    fields: dict[str, FieldProvenance] = {}
    for ref in summary_refs:
        if _has_date(ref):
            continue
        labels = _labels_without_values(ref)
        amounts = [(ref, token) for token in _money_tokens(ref.tokens)]
        if len(amounts) != 1:
            continue
        amount = _parse_money(amounts[0][1].text)
        if amount is None:
            continue
        for name, families in label_families.items():
            if labels in families and name not in operands:
                operands[name] = abs(amount)
                fields[name] = _provenance_refs((ref,), f"reconciliation_{name}")
    required = ("previous_balance", "current_billed_balance", "purchases_charges", "payments_credits", "financial_charges")
    missing = tuple(name for name in required if name not in operands)
    if missing or rejected:
        return ReconciliationEvidence(ReconciliationStatus.INSUFFICIENT_DATA, operands, missing_operands=missing, fields=fields)
    expected = operands["previous_balance"] + operands["purchases_charges"] + operands["financial_charges"] - operands["payments_credits"]
    difference = expected - operands["current_billed_balance"]
    return ReconciliationEvidence(ReconciliationStatus.RECONCILED if difference == 0 else ReconciliationStatus.NOT_RECONCILED, operands, difference=difference, fields=fields)


def _labels_without_values(ref: _LineRef) -> tuple[str, ...]:
    labels = []
    for token in ref.tokens:
        if _DATE_RE.search(token.text) or _MONEY_RE.match(token.text.replace("$", "")) or _label(token.text) in _CURRENCY:
            continue
        label = _label(token.text)
        if label:
            labels.append(label)
    if labels:
        labels[0] = re.sub(r"^\d+[.)-]?", "", labels[0])
    return tuple(label for label in labels if label)


def _provenance_refs(refs: tuple[_LineRef, ...], role: str, band_relation: str = "inside") -> FieldProvenance:
    return _provenance_items([(ref, token) for ref in refs for token in ref.tokens], role, band_relation)


def _provenance_items(items: Iterable[tuple[_LineRef, Token]], role: str, band_relation: str = "inside") -> FieldProvenance:
    by_page: dict[int, list[tuple[_LineRef, Token]]] = {}
    for ref, token in items:
        by_page.setdefault(ref.page.ordinal, []).append((ref, token))
    spans = []
    for page_ordinal in sorted(by_page):
        members = by_page[page_ordinal]
        lines = tuple(dict.fromkeys(ref.line.ordinal for ref, _ in members))
        tokens = tuple(dict.fromkeys(token.extraction_ordinal for _, token in members))
        bbox = BoundingBox.union(tuple(token.bbox for _, token in members))
        page = members[0][0].page
        normalized = tuple(
            (value / limit).quantize(Decimal("0.000001"))
            for value, limit in zip(
                (bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                (page.width, page.height, page.width, page.height),
            )
        )
        spans.append((page_ordinal, lines, tokens, bbox, page.width, page.height, normalized))
    if not spans:
        raise ValueError("provenance requires source evidence")
    first, *additional = spans
    return FieldProvenance(
        first[0], first[1], first[2], first[3], role, band_relation,
        tuple(
            AdditionalPageSpan(page, lines, tokens, bbox, width, height, normalized)
            for page, lines, tokens, bbox, width, height, normalized in additional
        ),
        first[4], first[5], first[6],
    )


def _with_role(provenance: FieldProvenance, role: str, band_relation: str) -> FieldProvenance:
    return FieldProvenance(
        provenance.page_ordinal, provenance.line_ordinals, provenance.token_ordinals,
        provenance.bbox, role, band_relation, provenance.additional_page_spans,
        provenance.page_width, provenance.page_height, provenance.normalized_bbox,
    )


def _ignored(ref: _LineRef, state: SectionState, reason: str, ordinal: int = 0) -> SourceRecord:
    return SourceRecord(RowOutcome.IGNORED, reason, ref.page.ordinal, state, ordinal, (ref.line.ordinal,), tuple(token.extraction_ordinal for token in ref.tokens), {"row": _provenance_refs((ref,), "row")})


def _rejected(ref: _LineRef, state: SectionState, ordinal: int, reason: str) -> SourceRecord:
    return SourceRecord(RowOutcome.REJECTED, reason, ref.page.ordinal, state, ordinal, (ref.line.ordinal,), tuple(token.extraction_ordinal for token in ref.tokens), {"row": _provenance_refs((ref,), "row")})
