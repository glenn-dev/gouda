from __future__ import annotations

from datetime import date
from io import BytesIO
from decimal import Decimal
import unittest

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from gouda.santander_tdc_pdf import (
    ContradictoryTdcPdfError, FinancialCategory, ReconciliationStatus,
    RowOutcome, SectionState, UnsupportedTdcPdfError, extract_tdc_pdf,
    parse_tdc_pdf, parse_tdc_pdf_gir,
)


def statement_pdf(*, rows: tuple[str, ...] = (), pages: int = 1, currency: bool = True) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=LETTER)
    content = (
        "Santander Tarjeta Crédito - Estado de cuenta",
        "Periodo: 01/01/2026 - 31/01/2026",
        "Fecha corte: 31/01/2026",
        "Fecha vencimiento: 15/02/2026",
        *(("Moneda: CLP",) if currency else ()),
        "Compras nacionales",
        "Fecha Detalle Moneda Monto",
        *rows,
    )
    for _ in range(pages):
        y = 750
        for value in content:
            document.drawString(40, y, value)
            y -= 16
        document.showPage()
    document.save()
    return output.getvalue()


def positioned_statement_pdf(
    *,
    body: tuple[tuple[tuple[str, int], ...] | str | int | None, ...],
    currency_label: bool = True,
    font_size: int = 12,
) -> bytes:
    """Build a synthetic statement with deterministic role-band geometry."""
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=LETTER)
    document.setFont("Helvetica", font_size)
    metadata = (
        "Santander Tarjeta Crédito - Estado de cuenta",
        "Periodo: 01/01/2026 - 31/01/2026",
        "Fecha corte: 31/01/2026",
        "Fecha vencimiento: 15/02/2026",
        *(("Moneda: CLP",) if currency_label else ()),
    )
    y = 750
    for value in metadata:
        document.drawString(40, y, value)
        y -= 16
    for item in body:
        if item is None:
            document.showPage()
            y = 750
            continue
        if isinstance(item, int):
            y = item
            continue
        if isinstance(item, str):
            document.drawString(40, y, item)
        else:
            for value, x in item:
                document.drawString(x, y, value)
        y -= 16
    document.showPage()
    document.save()
    return output.getvalue()


STANDARD_HEADER = (("Fecha", 40), ("Detalle", 110), ("Moneda", 420), ("Monto", 500))


def positioned_row(day: str, detail: str, amount: str, *, currency: str | None = "CLP"):
    values = [(day, 40), (detail, 110)]
    if currency is not None:
        values.append((currency, 420))
    values.append((amount, 500))
    return tuple(values)


class SantanderTdcPdfParserTests(unittest.TestCase):
    def test_parser_consumes_real_extraction_adapter_and_preserves_provenance(self):
        result = parse_tdc_pdf(statement_pdf(rows=("05/01 Compra sintetica CLP 1.234,56",)))
        self.assertEqual(result.parsed_count, 1)
        record = result.parsed_records[0]
        self.assertEqual(record.outcome, RowOutcome.PARSED)
        self.assertEqual(record.transaction_date.isoformat(), "2026-01-05")
        self.assertEqual(record.billed_amount, Decimal("1234.56"))
        self.assertEqual(record.billed_currency, "CLP")
        self.assertEqual(record.section_category, FinancialCategory.PURCHASE_CHARGE)
        self.assertEqual(record.debt_effect, Decimal("1234.56"))
        self.assertEqual(record.fields["row"].page_ordinal, 1)
        self.assertEqual(result.gir_version, "TDC-PDF-GIR-v1")
        self.assertTrue(result.extraction_profile_version)
        self.assertEqual(record.fields["billed_amount"].page_width, Decimal("612.00"))
        self.assertEqual(record.fields["billed_amount"].page_height, Decimal("792.00"))
        self.assertIsNotNone(record.fields["billed_amount"].normalized_bbox)
        self.assertGreater(record.row_group_ordinal, 0)

    def test_payment_and_future_activity_have_distinct_semantics(self):
        result = parse_tdc_pdf(statement_pdf(rows=(
            "Pagos",
            "Fecha Detalle Moneda Monto",
            "10/01 Pago sintetico CLP 100,00",
            "No facturado",
            "Fecha Detalle Moneda Monto",
            "20/01 Futuro sintetico CLP 55,00",
        )))
        parsed = result.parsed_records
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].section, SectionState.PAYMENTS_CREDITS)
        self.assertEqual(parsed[0].debt_effect, Decimal("-100.00"))
        self.assertTrue(any(row.reason_code == "unbilled_future" for row in result.records))

    def test_malformed_amount_is_rejected_inside_billed_state(self):
        result = parse_tdc_pdf(statement_pdf(rows=("05/01 Compra sintetica CLP no-es-monto",)))
        rejected = [row for row in result.records if row.outcome is RowOutcome.REJECTED]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reason_code, "amount_malformed")
        self.assertEqual(result.reconciliation.status, ReconciliationStatus.INSUFFICIENT_DATA)

    def test_missing_currency_is_rejected_even_when_a_symbol_is_present(self):
        result = parse_tdc_pdf(statement_pdf(rows=("05/01 Compra sintetica $ 10,00",), currency=False))
        rejected = [row for row in result.records if row.outcome is RowOutcome.REJECTED]
        self.assertEqual(rejected[0].reason_code, "currency_ambiguous")

    def test_unknown_financial_heading_fails_closed(self):
        source = statement_pdf(rows=("05/01 Compra sintetica CLP 10,00", "Nueva estructura 99,00"))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "unknown_heading_interrupts_financial_structure")

    def test_required_recognition_anchors_are_fatal(self):
        output = BytesIO()
        document = canvas.Canvas(output, pagesize=LETTER)
        document.drawString(40, 750, "Santander Tarjeta Crédito")
        document.save()
        with self.assertRaises(UnsupportedTdcPdfError) as context:
            parse_tdc_pdf(output.getvalue())
        self.assertEqual(context.exception.code, "cutoff_metadata_missing")

    def test_three_and_four_page_variation_is_accepted(self):
        for pages in (3, 4):
            result = parse_tdc_pdf(statement_pdf(rows=("05/01 Compra sintetica CLP 10,00",), pages=pages))
            self.assertEqual(result.status.value, "RECOGNIZED")

    def test_structural_section_categories_control_debt_effect(self):
        result = parse_tdc_pdf(statement_pdf(rows=(
            "05/01 Compra sintetica CLP 9,00",
            "Pagos", "Fecha Detalle Moneda Monto", "06/01 Pago sintetico CLP 10,00",
            "Creditos", "Fecha Detalle Moneda Monto", "07/01 Credito sintetico CLP 11,00",
            "Intereses", "Fecha Detalle Moneda Monto", "08/01 Interes sintetico CLP 12,00",
            "Comisiones", "Fecha Detalle Moneda Monto", "09/01 Comision sintetica CLP 13,00",
            "Impuestos", "Fecha Detalle Moneda Monto", "10/01 Impuesto sintetico CLP 14,00",
            "Seguros", "Fecha Detalle Moneda Monto", "11/01 Seguro sintetico CLP 15,00",
            "Avances", "Fecha Detalle Moneda Monto", "12/01 Avance sintetico CLP 16,00",
        )))

        categories = [record.section_category for record in result.parsed_records]
        effects = [record.debt_effect for record in result.parsed_records]
        self.assertEqual(categories, [
            FinancialCategory.PURCHASE_CHARGE,
            FinancialCategory.PAYMENT,
            FinancialCategory.CREDIT_REFUND,
            FinancialCategory.INTEREST,
            FinancialCategory.COMMISSION,
            FinancialCategory.TAX,
            FinancialCategory.INSURANCE,
            FinancialCategory.CASH_ADVANCE,
        ])
        self.assertEqual(effects, [Decimal("9.00"), Decimal("-10.00"), Decimal("-11.00"), Decimal("12.00"), Decimal("13.00"), Decimal("14.00"), Decimal("15.00"), Decimal("16.00")])

    def test_parsed_record_has_field_roles_and_header_profile_provenance(self):
        record = parse_tdc_pdf(statement_pdf(rows=("05/01 Compra sintetica CLP 10,00",))).parsed_records[0]
        self.assertEqual(record.header_profile, "domestic_billed")
        self.assertEqual(record.fields["transaction_date"].role, "transaction_date")
        self.assertEqual(record.fields["billed_amount"].role, "billed_amount")
        self.assertEqual(record.fields["header_profile"].role, "header_profile")
        self.assertEqual(record.fields["description_detail"].role, "description_detail")

    def test_arbitrary_unknown_heading_between_financial_rows_is_fatal(self):
        source = statement_pdf(rows=(
            "05/01 Synthetic alpha CLP 10,00",
            "Alternative structural block",
            "06/01 Synthetic beta CLP 11,00",
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "unknown_heading_interrupts_financial_structure")

    def test_description_anchor_words_do_not_change_category(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            (("Pagos seguros", 110),),
            positioned_row("06/01", "Synthetic beta", "11,00"),
        )))
        self.assertEqual(
            [record.section_category for record in result.parsed_records],
            [FinancialCategory.PURCHASE_CHARGE, FinancialCategory.PURCHASE_CHARGE],
        )

    def test_unknown_non_monetary_heading_interrupting_table_is_fatal(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales",
            STANDARD_HEADER,
            "Alternative structural block",
            positioned_row("05/01", "Synthetic alpha", "10,00"),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "unknown_heading_interrupts_financial_structure")

    def test_unbilled_to_billed_reversal_is_fatal(self):
        source = statement_pdf(rows=(
            "05/01 Synthetic alpha CLP 10,00",
            "No facturado", "Fecha Detalle Moneda Monto",
            "06/01 Synthetic future CLP 11,00",
            "Compras nacionales", "Fecha Detalle Moneda Monto",
            "07/01 Synthetic beta CLP 12,00",
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "contradictory_section_transition")

    def test_cross_page_continuation_requires_compatible_repeated_header(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales",
            STANDARD_HEADER,
            (("05/01", 40), ("Synthetic alpha", 110)),
            None,
            (("10,00", 500),),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "unproven_cross_page_continuation")

    def test_new_page_financial_row_requires_page_local_repeated_header(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            None,
            positioned_row("06/01", "Synthetic beta", "11,00"),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "transaction_header_missing_on_page")

    def test_financial_looking_row_in_preamble_is_fatal(self):
        source = positioned_statement_pdf(body=(
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("06/01", "Synthetic beta", "11,00"),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "financial_content_outside_recognized_state")

    def test_financial_looking_row_after_footer_transition_is_fatal(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            "Mensajes",
            positioned_row("06/01", "Synthetic beta", "11,00"),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "financial_content_outside_recognized_state")

    def test_unlabeled_currency_token_is_not_inherited(self):
        result = parse_tdc_pdf(positioned_statement_pdf(currency_label=False, body=(
            (("CLP", 40),),
            "Compras nacionales",
            STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00", currency=None),
        )))
        rejected = [record for record in result.records if record.outcome is RowOutcome.REJECTED]
        self.assertEqual([record.reason_code for record in rejected], ["currency_ambiguous"])

    def test_reordered_monetary_header_roles_are_fatal(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales",
            (("Fecha", 40), ("Detalle", 110), ("Total", 400), ("Cargo", 500)),
            (("05/01", 40), ("Synthetic alpha", 110), ("20,00", 400), ("10,00", 500)),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "unsupported_column_order")

    def test_transaction_descriptions_cannot_supply_reconciliation_operands(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales",
            STANDARD_HEADER,
            positioned_row("05/01", "saldo anterior", "10,00"),
            positioned_row("06/01", "saldo actual", "15,00"),
            positioned_row("07/01", "compras", "5,00"),
            positioned_row("08/01", "pagos", "2,00"),
            positioned_row("09/01", "intereses", "2,00"),
        ))
        result = parse_tdc_pdf(source)
        self.assertEqual(result.reconciliation.status, ReconciliationStatus.INSUFFICIENT_DATA)
        self.assertEqual(dict(result.reconciliation.operands), {})

    def test_parser_result_mappings_are_deeply_immutable(self):
        result = parse_tdc_pdf(statement_pdf(rows=("05/01 Synthetic alpha CLP 10,00",)))
        record = result.parsed_records[0]
        with self.assertRaises(TypeError):
            record.fields["injected"] = record.fields["row"]
        with self.assertRaises(TypeError):
            result.metadata.fields["injected"] = record.fields["row"]
        with self.assertRaises(TypeError):
            result.reconciliation.operands["injected"] = Decimal("1")

    def test_constructor_input_mappings_are_defensively_copied(self):
        from gouda.santander_tdc_pdf import FieldProvenance, SourceRecord

        provenance = FieldProvenance(1, (1,), (1,), object(), "row")
        source_fields = {"row": provenance}
        record = SourceRecord(
            RowOutcome.IGNORED, "synthetic", 1, SectionState.PREAMBLE,
            0, (1,), (1,), source_fields,
        )
        source_fields["injected"] = provenance
        self.assertEqual(tuple(record.fields), ("row",))

    def test_header_profile_provenance_points_to_actual_header(self):
        gir = extract_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
        )))
        record = parse_tdc_pdf_gir(gir).parsed_records[0]
        header = record.fields["header_profile"]
        transaction = record.fields["transaction_date"]
        self.assertEqual(header.page_ordinal, 1)
        self.assertNotEqual(header.line_ordinals, transaction.line_ordinals)
        page = gir.pages[0]
        header_line = next(line for line in page.lines if line.ordinal == header.line_ordinals[0])
        self.assertTrue(set(header.token_ordinals).issubset(header_line.token_ordinals))

    def test_row_group_ordinals_restart_for_each_financial_section(self):
        result = parse_tdc_pdf(statement_pdf(rows=(
            "05/01 Synthetic alpha CLP 10,00",
            "06/01 Synthetic beta CLP 11,00",
            "Pagos", "Fecha Detalle Moneda Monto",
            "07/01 Synthetic payment CLP 12,00",
        )))
        self.assertEqual(
            [(record.section, record.row_group_ordinal) for record in result.parsed_records],
            [
                (SectionState.BILLED_DOMESTIC, 1),
                (SectionState.BILLED_DOMESTIC, 2),
                (SectionState.PAYMENTS_CREDITS, 1),
            ],
        )

    def test_inherited_currency_has_source_context_provenance(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00", currency=None),
        )))
        record = result.parsed_records[0]
        self.assertEqual(record.billed_currency, "CLP")
        inherited = record.fields["billed_currency"]
        source = result.metadata.fields["statement_currency"]
        self.assertEqual((inherited.page_ordinal, inherited.line_ordinals, inherited.token_ordinals),
                         (source.page_ordinal, source.line_ordinals, source.token_ordinals))
        self.assertEqual(inherited.band_relation, "inherited_statement_context")

    def test_statement_period_has_provenance(self):
        result = parse_tdc_pdf(statement_pdf(rows=("05/01 Synthetic alpha CLP 10,00",)))
        self.assertIn("statement_period", result.metadata.fields)
        self.assertEqual(result.metadata.fields["statement_period"].role, "statement_period")

    def test_conflicting_repeated_header_is_fatal(self):
        source = positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            (("Fecha", 40), ("Detalle", 110), ("Monto", 420), ("Moneda", 500)),
            (("06/01", 40), ("Synthetic beta", 110), ("11,00", 420), ("CLP", 500)),
        ))
        with self.assertRaises(ContradictoryTdcPdfError) as context:
            parse_tdc_pdf(source)
        self.assertEqual(context.exception.code, "incompatible_repeated_header")

    def test_malformed_financial_candidate_is_rejected_not_ignored(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            (("Synthetic total", 110), ("CLP", 420), ("10,00", 500)),
        )))
        rejected = [record for record in result.records if record.outcome is RowOutcome.REJECTED]
        self.assertEqual([record.reason_code for record in rejected], ["date_invalid"])

    def test_valid_repeated_header_preserves_section_local_order(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            STANDARD_HEADER,
            positioned_row("06/01", "Synthetic beta", "11,00"),
        )))
        self.assertEqual(result.parsed_count, 2)
        self.assertEqual([record.row_group_ordinal for record in result.parsed_records], [1, 2])
        self.assertTrue(any(record.reason_code == "repeated_header" for record in result.records))

    def test_valid_multiline_description_uses_description_band_only(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            (("Synthetic continuation", 110),),
        )))
        record = result.parsed_records[0]
        self.assertIn("Synthetic continuation", record.description_detail)
        self.assertEqual(len(record.fields["description_detail"].line_ordinals), 2)

    def test_valid_cross_page_description_continuation_requires_repeated_header(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            None,
            STANDARD_HEADER,
            (("Synthetic continuation", 110),),
        )))
        record = result.parsed_records[0]
        self.assertEqual(record.description_detail, "Synthetic alpha Synthetic continuation")
        self.assertEqual(len(record.fields["row"].additional_page_spans), 1)
        self.assertEqual(record.fields["row"].additional_page_spans[0].page_ordinal, 2)
        self.assertEqual(record.fields["row"].additional_page_spans[0].page_width, Decimal("612.00"))
        self.assertIsNotNone(record.fields["row"].additional_page_spans[0].normalized_bbox)

    def test_international_profile_accepts_explicit_row_currency(self):
        result = parse_tdc_pdf(positioned_statement_pdf(currency_label=False, body=(
            "Compras internacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic international", "10,00", currency="USD"),
        )))
        record = result.parsed_records[0]
        self.assertEqual(record.header_profile, "international_billed")
        self.assertEqual(record.billed_currency, "USD")
        self.assertEqual(record.section_category, FinancialCategory.PURCHASE_CHARGE)

    def test_explicit_installment_profile_preserves_only_proven_fields(self):
        installment_header = (
            ("Fecha", 40), ("Detalle", 110), ("Cuota", 330),
            ("Importe", 400), ("Cargo", 500),
        )
        installment_row = (
            ("05/01", 40), ("Synthetic installment", 110), ("2", 330),
            ("4,00", 400), ("10,00", 500),
        )
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras en cuotas", installment_header, installment_row,
        )))
        record = result.parsed_records[0]
        self.assertEqual(record.header_profile, "installment_billed")
        self.assertEqual(record.installment_number, 2)
        self.assertEqual(record.installment_amount, Decimal("4.00"))
        self.assertEqual(record.billed_amount, Decimal("10.00"))
        self.assertEqual(record.fields["installment_number"].role, "installment_number")
        self.assertEqual(record.fields["installment_amount"].role, "installment_amount")

    def test_all_mapping_constructors_defensively_copy_inputs(self):
        from gouda.santander_tdc_pdf import (
            FieldProvenance, ReconciliationEvidence, StatementMetadata,
        )

        provenance = FieldProvenance(1, (1,), (1,), object(), "synthetic")
        metadata_fields = {"statement_period": provenance}
        operands = {"previous_balance": Decimal("1")}
        reconciliation_fields = {"previous_balance": provenance}
        metadata = StatementMetadata(
            date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 31),
            date(2026, 2, 15), "credit_card", "CLP", metadata_fields,
        )
        evidence = ReconciliationEvidence(
            ReconciliationStatus.INSUFFICIENT_DATA, operands,
            missing_operands=("current_billed_balance",), fields=reconciliation_fields,
        )
        metadata_fields["injected"] = provenance
        operands["injected"] = Decimal("2")
        reconciliation_fields["injected"] = provenance
        self.assertNotIn("injected", metadata.fields)
        self.assertNotIn("injected", evidence.operands)
        self.assertNotIn("injected", evidence.fields)

    def test_observed_current_installment_profile_uses_explicit_primary_charge_band(self):
        observed_header = (
            ("Lugar", 40), ("de", 66), ("Fecha", 103), ("de", 129),
            ("Descripcion", 152), ("operacion", 203), ("o", 247),
            ("cobro", 254), ("Monto", 395), ("Monto", 450),
            ("Cargo", 515), ("del", 543), ("mes", 559),
        )
        header_continuations = (
            (("operacion", 40), ("operacion", 103), ("origen", 395), ("total", 450), ("a", 475)),
            (("NoCuota", 502), ("Valor", 542), ("cuota", 568)),
            (("operacion", 395), ("pagar", 450)),
            (("mensual", 551),),
            (("o", 395), ("cobro", 402)),
        )
        row = (
            ("12345678901", 40), ("05/01", 119), ("Synthetic", 152),
            ("SYN", 324), ("4,00", 414), ("10,00", 570),
        )
        result = parse_tdc_pdf(positioned_statement_pdf(currency_label=False, font_size=7, body=(
            "Estado de cuenta en moneda nacional de tarjeta de credito",
            "2.Periodo actual", observed_header, *header_continuations, row,
        )))
        record = result.parsed_records[0]
        self.assertEqual(record.header_profile, "installment_billed")
        self.assertEqual(record.billed_currency, "CLP")
        self.assertEqual(record.billed_amount, Decimal("10.00"))
        self.assertEqual(record.location, "12345678901")
        self.assertEqual(record.reference_authorization, "SYN")
        self.assertEqual(len(record.fields["header_profile"].line_ordinals), 6)
        self.assertNotIn("installment_amount", record.fields)

    def test_stable_page_bottom_boundary_closes_group_before_footer_content(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            100,
            "Synthetic page footer",
        )))
        self.assertEqual(result.parsed_count, 1)
        self.assertTrue(any(record.reason_code == "page_chrome" for record in result.records))

    def test_numbered_payment_information_boundary_is_ignored_not_parsed(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "10,00"),
            "III. Información de pago",
            (("Saldo capital", 40), ("20,00", 500)),
        )))
        self.assertEqual(result.parsed_count, 1)
        self.assertEqual(result.rejected_count, 0)
        self.assertTrue(any(record.section is SectionState.FOOTER_LEGAL for record in result.records))

    def test_complete_explicit_summary_operands_reconcile_with_provenance(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            (("Saldo anterior", 40), ("10,00", 500)),
            (("Saldo actual", 40), ("15,00", 500)),
            (("Total compras", 40), ("5,00", 500)),
            (("Total pagos", 40), ("2,00", 500)),
            (("Total intereses", 40), ("2,00", 500)),
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "5,00"),
        )))
        self.assertEqual(result.reconciliation.status, ReconciliationStatus.RECONCILED)
        self.assertEqual(
            set(result.reconciliation.fields),
            {"previous_balance", "current_billed_balance", "purchases_charges", "payments_credits", "financial_charges"},
        )

    def test_complete_explicit_summary_arithmetic_mismatch_is_not_reconciled(self):
        result = parse_tdc_pdf(positioned_statement_pdf(body=(
            (("Saldo anterior", 40), ("10,00", 500)),
            (("Saldo actual", 40), ("14,00", 500)),
            (("Total compras", 40), ("5,00", 500)),
            (("Total pagos", 40), ("2,00", 500)),
            (("Total intereses", 40), ("2,00", 500)),
            "Compras nacionales", STANDARD_HEADER,
            positioned_row("05/01", "Synthetic alpha", "5,00"),
        )))
        self.assertEqual(result.reconciliation.status, ReconciliationStatus.NOT_RECONCILED)
        self.assertEqual(result.reconciliation.difference, Decimal("1.00"))


if __name__ == "__main__":
    unittest.main()
