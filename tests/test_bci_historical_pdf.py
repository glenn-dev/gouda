from dataclasses import replace
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from gouda.bci_historical_pdf import (
    BciParserStatus,
    BciReconciliationStatus,
    BciRowOutcome,
    extract_bci_historical_pdf,
    parse_bci_historical_pdf,
)
from gouda.bci_historical_pdf.parser import parse_bci_historical_pdf_gir
from tests.fixtures.bci_historical import _pdf, synthetic_bci_historical_pdf


class BciHistoricalPdfParserTests(SimpleTestCase):
    def test_supported_rows_signs_provenance_and_reconciliation(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=(
            {"date": date(2026, 1, 2), "debit": 1000, "reference": "R-1"},
            {"date": date(2026, 1, 2), "credit": 2500, "reference": "R-1"},
        )))
        self.assertIs(result.status, BciParserStatus.RECOGNIZED)
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.RECONCILED)
        self.assertEqual(result.parsed_count, 2)
        self.assertEqual(result.parsed_records[0].signed_amount, Decimal("-1000.00"))
        self.assertEqual(result.parsed_records[1].signed_amount, Decimal("2500.00"))
        self.assertIsNone(result.parsed_records[0].transaction_date)
        self.assertEqual(result.parsed_records[0].fields["row"].page_ordinal, 1)
        self.assertEqual(result.parsed_records[0].fields["row"].token_ordinals, result.parsed_records[0].token_ordinals)

    def test_page_continuation_and_repeated_tuple_survive(self):
        rows = tuple({"date": date(2026, 1, 2), "debit": 1000, "reference": "SAME"} for _ in range(16))
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=rows))
        self.assertEqual(result.parsed_count, 16)
        self.assertEqual([row.source_row_ordinal for row in result.parsed_records], list(range(1, 17)))
        self.assertEqual([record.reason_code for record in result.records if record.outcome is BciRowOutcome.IGNORED], ["table_header", "page_continuation", "period_summary"])
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.RECONCILED)

    def test_physical_page_order_is_required(self):
        gir = extract_bci_historical_pdf(synthetic_bci_historical_pdf())
        reordered = replace(gir, pages=tuple(replace(page, ordinal=page.ordinal + 1) for page in gir.pages))
        result = parse_bci_historical_pdf_gir(reordered)
        self.assertIs(result.status, BciParserStatus.FATAL)
        self.assertEqual(result.errors, ("page_number_invalid",))

    def test_wrong_product_is_fatal_without_records(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(wrong_product=True))
        self.assertIs(result.status, BciParserStatus.FATAL)
        self.assertEqual(result.errors, ("source_identity_mismatch",))
        self.assertEqual(result.records, ())

    def test_missing_operand_is_insufficient_data(self):
        for operand in ("opening", "debits", "credits", "closing"):
            with self.subTest(operand=operand):
                result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},), omit_summary_operand=operand))
                self.assertIs(result.status, BciParserStatus.RECOGNIZED)
                self.assertEqual(result.reconciliation.status, BciReconciliationStatus.INSUFFICIENT_DATA)
                self.assertEqual(result.reconciliation.missing_operands, {
                    "opening": ("opening_balance",),
                    "debits": ("printed_total_debits",),
                    "credits": ("printed_total_credits",),
                    "closing": ("closing_balance",),
                }[operand])
                self.assertEqual(result.parsed_count, 1)

    def test_contradictory_summary_period_fails_closed(self):
        result = parse_bci_historical_pdf(
            synthetic_bci_historical_pdf(
                rows=({"debit": 1000},),
                summary_period_override=(date(2026, 2, 1), date(2026, 2, 28)),
            )
        )
        self.assertIs(result.status, BciParserStatus.FATAL)
        self.assertEqual(result.errors, ("period_summary_mismatch",))

    def test_non_pdf_is_sanitized_fatal(self):
        result = parse_bci_historical_pdf(b"not a pdf")
        self.assertIs(result.status, BciParserStatus.FATAL)
        self.assertEqual(result.errors, ("pdf_invalid",))

    def test_reconciliation_failure_remains_recognized(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},), closing_override=99999))
        self.assertIs(result.status, BciParserStatus.RECOGNIZED)
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.NOT_RECONCILED)
        self.assertEqual(result.parsed_count, 1)

    def test_reconciliation_checks_are_independent(self):
        normal = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},)))
        self.assertEqual({name: check.status.value for name, check in normal.reconciliation.checks.items()}, {
            "running_balance_continuity": "PASS",
            "summary_balance_equation": "PASS",
            "parsed_totals_match_printed": "PASS",
            "final_running_balance_matches": "PASS",
        })
        broken_chain = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=(
            {"debit": 1000, "balance": 99999},
            {"debit": 1000, "balance": 98000},
        )))
        self.assertEqual(broken_chain.reconciliation.checks["running_balance_continuity"].status.value, "FAIL")
        self.assertEqual(broken_chain.reconciliation.checks["final_running_balance_matches"].status.value, "PASS")
        wrong_totals = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},), printed_total_debits_override=2000, closing_override=98000))
        self.assertEqual(wrong_totals.reconciliation.checks["summary_balance_equation"].status.value, "PASS")
        self.assertEqual(wrong_totals.reconciliation.checks["parsed_totals_match_printed"].status.value, "FAIL")
        wrong_closing = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},), closing_override=99999))
        self.assertEqual(wrong_closing.reconciliation.checks["parsed_totals_match_printed"].status.value, "PASS")
        self.assertEqual(wrong_closing.reconciliation.checks["final_running_balance_matches"].status.value, "FAIL")

    def test_malformed_date_candidate_is_rejected(self):
        content = synthetic_bci_historical_pdf(
            period_start=date(2099, 1, 1),
            period_end=date(2099, 1, 31),
            rows=({"date": date(2099, 1, 2), "debit": 1000},),
        ).replace(b"02/01/2099", b"xx/xx/xxxx")
        result = parse_bci_historical_pdf(content)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.rejected_records[0].reason_code, "date_invalid")
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.INSUFFICIENT_DATA)

    def test_out_of_period_and_backward_dates_are_rejected(self):
        out_of_period = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"date": date(2026, 2, 1), "debit": 1000},)))
        self.assertEqual(out_of_period.rejected_records[0].reason_code, "date_outside_period")
        backward = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=(
            {"date": date(2026, 1, 3), "debit": 1000},
            {"date": date(2026, 1, 2), "credit": 1000},
        )))
        self.assertEqual(backward.rejected_records[0].reason_code, "date_order_invalid")
        self.assertEqual(backward.reconciliation.status, BciReconciliationStatus.INSUFFICIENT_DATA)

    def test_negative_balances_and_zero_crossing_are_exact(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(
            opening_balance=100,
            rows=(
                {"date": date(2026, 1, 1), "debit": 100},
                {"date": date(2026, 1, 2), "credit": 50},
                {"date": date(2026, 1, 3), "debit": 100},
            ),
        ))
        self.assertEqual([row.running_balance for row in result.parsed_records], [Decimal("0.00"), Decimal("50.00"), Decimal("-50.00")])
        self.assertEqual(result.metadata.opening_balance, Decimal("100.00"))
        self.assertEqual(result.metadata.closing_balance, Decimal("-50.00"))
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.RECONCILED)
        negative_opening = parse_bci_historical_pdf(synthetic_bci_historical_pdf(opening_balance=-100))
        self.assertEqual(negative_opening.metadata.opening_balance, Decimal("-100.00"))
        self.assertEqual(negative_opening.reconciliation.status, BciReconciliationStatus.RECONCILED)

    def test_directional_amount_rejections_are_distinct(self):
        cases = (
            ({"debit": 100, "credit": 1}, "amount_both_sides"),
            ({"debit": 0, "credit": 0}, "amount_missing"),
            ({"debit": 0, "emit_debit_zero": True}, "zero_amount_unsupported"),
            ({"debit": -100}, "negative_directional_amount"),
            ({"debit": 0, "debit_text": "1.00"}, "amount_invalid"),
            ({"debit": 0, "debit_text": "999999999999999999999999"}, "money_precision_overflow"),
        )
        for row, reason in cases:
            with self.subTest(reason=reason):
                result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=(row,)))
                self.assertEqual(result.rejected_count, 1)
                self.assertEqual(result.parsed_records, ())
                self.assertEqual(result.rejected_records[0].reason_code, reason)
                self.assertEqual(result.reconciliation.status, BciReconciliationStatus.INSUFFICIENT_DATA)

    def test_zero_transaction_statement_reconciles_without_observations(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf())
        self.assertEqual(result.parsed_count, 0)
        self.assertEqual(result.rejected_count, 0)
        self.assertEqual(result.ignored_count, 2)
        self.assertEqual([record.reason_code for record in result.records], ["table_header", "period_summary"])
        self.assertEqual(result.reconciliation.status, BciReconciliationStatus.RECONCILED)

    def test_summary_provenance_points_to_value_tokens(self):
        content = synthetic_bci_historical_pdf(rows=({"debit": 1000},))
        gir = extract_bci_historical_pdf(content)
        result = parse_bci_historical_pdf(content)
        value_line = gir.pages[-1].lines[-1]
        value_tokens = [token for token in gir.pages[-1].tokens if token.extraction_ordinal in value_line.token_ordinals]
        bands = {
            "opening_balance": (280, 350),
            "printed_total_debits": (350, 426),
            "printed_total_credits": (426, 505),
            "closing_balance": (535, 605),
        }
        for name, (left, right) in bands.items():
            expected = tuple(token.extraction_ordinal for token in value_tokens if left <= token.bbox.x0 < right)
            self.assertEqual(result.metadata.fields[name].token_ordinals, expected)
            self.assertTrue(expected)

    def test_duplicate_summary_operand_fails_closed(self):
        result = parse_bci_historical_pdf(synthetic_bci_historical_pdf(rows=({"debit": 1000},), duplicate_summary_operand="debits"))
        self.assertIs(result.status, BciParserStatus.FATAL)
        self.assertEqual(result.errors, ("period_summary_ambiguous",))

    def test_structural_failures_are_fatal(self):
        cases = (
            (b"%PDF-1.4\ncorrupt", "pdf_invalid"),
            (b"%PDF-1.4\n/Encrypt", "pdf_encrypted_unsupported"),
            (_pdf([[]]), "native_text_required"),
            (synthetic_bci_historical_pdf(omit_header_period=True), "period_missing"),
            (synthetic_bci_historical_pdf(currency_text="DOLLARS"), "currency_missing"),
            (synthetic_bci_historical_pdf(header_variant="reordered"), "unsupported_financial_table_geometry"),
            (synthetic_bci_historical_pdf(rows=tuple({"debit": 1000} for _ in range(16)), header_variant="continuation_wrong"), "unsupported_financial_table_geometry"),
            (synthetic_bci_historical_pdf(page_size=(612, 800)), "source_variant_unsupported"),
        )
        for content, error in cases:
            with self.subTest(error=error):
                result = parse_bci_historical_pdf(content)
                self.assertIs(result.status, BciParserStatus.FATAL)
                self.assertEqual(result.errors, (error,))
        truncated = parse_bci_historical_pdf(synthetic_bci_historical_pdf()[:-20])
        self.assertIs(truncated.status, BciParserStatus.FATAL)
        self.assertEqual(truncated.errors, ("pdf_invalid",))
