from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from struct import pack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import xlrd
from xlrd.biffh import XL_EOF, XL_FORMULA

from gouda.bci_current_cartola_xls import (
    AmbiguousWorksheetError,
    MalformedWorkbookError,
    RowOutcome,
    UnsupportedWorkbookError,
    parse_bci_current_cartola_xls,
)
from gouda.bci_current_cartola_xls.parser import (
    _CFB_SIGNATURE,
    _formula_coordinates,
    _parse_sheets,
    _read_legacy_xls,
)
from gouda.bci_current_cartola_xls.types import SourceCell
from tests.fixtures.bci_current_cartola import (
    HEADERS,
    synthetic_current_cartola_sheet,
    text_cell,
    with_cell,
)


class BciCurrentCartolaParserTests(unittest.TestCase):
    def parse_sheet(self, sheet=None, *, sheets=None):
        selected = tuple(sheets or (sheet or synthetic_current_cartola_sheet(),))
        return _parse_sheets(selected, artifact_identity="synthetic-artifact")

    def test_supported_profile_preserves_source_native_fields(self):
        result = self.parse_sheet()

        self.assertEqual(result.source_variant, "bci_current_cartola_xls")
        self.assertEqual(result.parser_version, "bci_current_cartola_v0.1")
        self.assertEqual(result.contract_version, "bci_current_cartola_v0.1")
        self.assertEqual(result.sheet_count, 1)
        self.assertEqual(result.parsed_count, 2)
        self.assertEqual(result.ignored_count, 9)
        self.assertEqual(result.rejected_count, 0)

        debit, credit = result.parsed_records
        self.assertEqual(debit.source_date, date(2031, 8, 25))
        self.assertEqual(debit.source_description, "Synthetic purchase")
        self.assertEqual(debit.source_series, "opaque-A")
        self.assertEqual(debit.source_signed_amount, Decimal("-1234.00"))
        self.assertEqual(debit.source_balance, Decimal("8000.00"))
        self.assertEqual(credit.source_signed_amount, Decimal("500.00"))
        self.assertFalse(hasattr(debit, "signed_amount"))

    def test_exact_title_metadata_separator_and_headers_are_required(self):
        changed_title = synthetic_current_cartola_sheet(title="Unsupported title")
        changed_metadata = synthetic_current_cartola_sheet(
            metadata=("Changed label",) + tuple(
                synthetic_current_cartola_sheet().rows[row]["B"].value for row in range(3, 8)
            )
        )
        changed_headers = synthetic_current_cartola_sheet(
            headers=HEADERS[:3] + ("Changed amount",) + HEADERS[4:]
        )
        changed_separator = with_cell(synthetic_current_cartola_sheet(), 8, "A", text_cell("Unexpected"))

        for sheet in (changed_title, changed_metadata, changed_headers, changed_separator):
            with self.subTest(sheet=sheet):
                with self.assertRaises(UnsupportedWorkbookError):
                    self.parse_sheet(sheet)

    def test_positive_negative_and_zero_source_values_are_preserved(self):
        sheet = synthetic_current_cartola_sheet(
            transactions=[
                {"date": "25-08-2031", "description": "Synthetic A", "series": "opaque", "amount": "-10", "balance": "-5"},
                {"date": "24-08-2031", "description": "Synthetic B", "series": "opaque", "amount": "0", "balance": "0"},
                {"date": "23-08-2031", "description": "Synthetic C", "series": "opaque", "amount": "10", "balance": "5"},
            ]
        )

        records = self.parse_sheet(sheet).parsed_records

        self.assertEqual([record.source_signed_amount for record in records], [Decimal("-10.00"), Decimal("0.00"), Decimal("10.00")])
        self.assertEqual([record.source_balance for record in records], [Decimal("-5.00"), Decimal("0.00"), Decimal("5.00")])

    def test_series_is_opaque_and_may_repeat_or_be_empty(self):
        sheet = synthetic_current_cartola_sheet(
            transactions=[
                {"date": "25-08-2031", "description": "Same", "series": "opaque-repeat", "amount": "1", "balance": "1"},
                {"date": "25-08-2031", "description": "Same", "series": "opaque-repeat", "amount": "2", "balance": "3"},
                {"date": "24-08-2031", "description": "", "series": "", "amount": "3", "balance": "6"},
            ]
        )

        records = self.parse_sheet(sheet).parsed_records

        self.assertEqual([record.source_series for record in records], ["opaque-repeat", "opaque-repeat", None])
        self.assertEqual(records[-1].source_description, None)

    def test_date_grammar_and_real_dates_are_enforced(self):
        for invalid in ("25/08/2031", "5-08-2031", "31-02-2031", "25-08-31"):
            with self.subTest(invalid=invalid):
                sheet = synthetic_current_cartola_sheet(
                    transactions=[{"date": invalid, "description": "Synthetic", "series": "opaque", "amount": "1", "balance": "1"}]
                )
                self.assertEqual(self.parse_sheet(sheet).records[-1].error_codes, ("date_invalid",))

    def test_source_dates_must_be_non_increasing_and_equal_dates_are_supported(self):
        valid = synthetic_current_cartola_sheet(
            transactions=[
                {"date": "25-08-2031", "description": "A", "series": "x", "amount": "1", "balance": "1"},
                {"date": "25-08-2031", "description": "B", "series": "x", "amount": "1", "balance": "2"},
            ]
        )
        invalid = synthetic_current_cartola_sheet(
            transactions=[
                {"date": "24-08-2031", "description": "A", "series": "x", "amount": "1", "balance": "1"},
                {"date": "25-08-2031", "description": "B", "series": "x", "amount": "1", "balance": "2"},
            ]
        )

        self.assertEqual(self.parse_sheet(valid).parsed_count, 2)
        self.assertEqual(self.parse_sheet(invalid).records[-1].error_codes, ("source_date_order_invalid",))

    def test_money_grammar_rejects_grouping_fraction_symbol_and_plus_sign(self):
        for invalid in ("12.34", "1,234", "1.25", "$100", "+100", "--100"):
            with self.subTest(invalid=invalid):
                sheet = synthetic_current_cartola_sheet(
                    transactions=[{"date": "25-08-2031", "description": "Synthetic", "series": "x", "amount": invalid, "balance": "1"}]
                )
                self.assertIn("amount_invalid", self.parse_sheet(sheet).records[-1].error_codes)

    def test_money_overflow_is_rejected_without_rounding(self):
        sheet = synthetic_current_cartola_sheet(
            transactions=[{"date": "25-08-2031", "description": "Synthetic", "series": "x", "amount": "9999999999999999999", "balance": "1"}]
        )

        self.assertEqual(self.parse_sheet(sheet).records[-1].error_codes, ("amount_precision_overflow",))

    def test_balance_uses_the_same_exact_grammar_and_overflow_boundary(self):
        invalid = synthetic_current_cartola_sheet(
            transactions=[{"date": "25-08-2031", "description": "Synthetic", "series": "x", "amount": "1", "balance": "1.25"}]
        )
        overflow = synthetic_current_cartola_sheet(
            transactions=[{"date": "25-08-2031", "description": "Synthetic", "series": "x", "amount": "1", "balance": "9999999999999999999"}]
        )

        self.assertEqual(self.parse_sheet(invalid).records[-1].error_codes, ("balance_invalid",))
        self.assertEqual(self.parse_sheet(overflow).records[-1].error_codes, ("balance_precision_overflow",))

    def test_formula_and_native_numeric_transaction_cells_are_rejected(self):
        formula = SourceCell(value="cached", cell_type="formula", is_formula=True, present=True)
        numeric = SourceCell(value=100.0, cell_type="number", present=True)

        formula_sheet = with_cell(synthetic_current_cartola_sheet(), 10, "D", formula)
        numeric_sheet = with_cell(synthetic_current_cartola_sheet(), 10, "D", numeric)

        self.assertEqual(self.parse_sheet(formula_sheet).records[9].error_codes, ("formula_unsupported",))
        self.assertEqual(self.parse_sheet(numeric_sheet).records[9].error_codes, ("cell_type_unsupported",))

    def test_formula_or_native_type_in_recognition_region_fails_workbook(self):
        formula = SourceCell(value="cached", cell_type="formula", is_formula=True, present=True)
        numeric = SourceCell(value=100.0, cell_type="number", present=True)

        for sheet in (
            with_cell(synthetic_current_cartola_sheet(), 3, "C", formula),
            with_cell(synthetic_current_cartola_sheet(), 3, "C", numeric),
        ):
            with self.subTest(sheet=sheet):
                with self.assertRaises(UnsupportedWorkbookError):
                    self.parse_sheet(sheet)

    def test_changed_merge_and_geometry_fail_closed(self):
        changed_merge = synthetic_current_cartola_sheet(title_merge="A1:D1")
        extra_column = replace(
            synthetic_current_cartola_sheet(),
            physical_ncols=6,
            actual_max_column=6,
            populated_columns=(1, 2, 3, 4, 5, 6),
        )

        for sheet in (changed_merge, extra_column):
            with self.subTest(sheet=sheet):
                with self.assertRaises(UnsupportedWorkbookError):
                    self.parse_sheet(sheet)

    def test_structural_gap_fails_closed(self):
        sheet = synthetic_current_cartola_sheet()
        rows = dict(sheet.rows)
        rows[10] = {column: SourceCell() for column in "ABCDE"}
        sheet = replace(sheet, rows=rows, populated_rows=tuple(row for row in sheet.populated_rows if row != 10))

        with self.assertRaises(UnsupportedWorkbookError) as context:
            self.parse_sheet(sheet)
        self.assertEqual(context.exception.code, "unexpected_empty_row")

    def test_extra_sheet_and_multiple_matching_sheets_fail_closed(self):
        first = synthetic_current_cartola_sheet()
        nonmatching = synthetic_current_cartola_sheet(title="Other", name="Other", ordinal=2)
        matching = synthetic_current_cartola_sheet(name="Second", ordinal=2)

        with self.assertRaises(UnsupportedWorkbookError) as extra:
            self.parse_sheet(sheets=(first, nonmatching))
        self.assertEqual(extra.exception.code, "worksheet_count_unsupported")
        with self.assertRaises(AmbiguousWorksheetError):
            self.parse_sheet(sheets=(first, matching))

    def test_hidden_only_sheet_is_not_recognized(self):
        with self.assertRaises(UnsupportedWorkbookError):
            self.parse_sheet(synthetic_current_cartola_sheet(visible=False))

    def test_public_parser_rejects_non_cfb_input(self):
        with self.assertRaises(MalformedWorkbookError) as context:
            parse_bci_current_cartola_xls(b"not-a-legacy-xls")
        self.assertEqual(context.exception.code, "xls_invalid")

    def test_public_parser_maps_unreadable_source_to_sanitized_failure(self):
        with self.assertRaises(MalformedWorkbookError) as context:
            parse_bci_current_cartola_xls("synthetic-missing-current-cartola.xls")
        self.assertEqual(context.exception.code, "xls_invalid")

    def test_public_parser_routes_cfb_bytes_through_thin_xlrd_adapter(self):
        sheet = synthetic_current_cartola_sheet()
        with patch(
            "gouda.bci_current_cartola_xls.parser._read_legacy_xls",
            return_value=(sheet,),
        ) as reader:
            result = parse_bci_current_cartola_xls(
                _CFB_SIGNATURE + b"synthetic container tail",
                artifact_identity="synthetic-artifact",
            )

        reader.assert_called_once()
        self.assertEqual(result.parsed_count, 2)

    def test_xlrd_adapter_is_read_only_on_demand_and_suppresses_diagnostics(self):
        workbook = SimpleNamespace(nsheets=0)
        workbook.release_resources = Mock()
        with patch("gouda.bci_current_cartola_xls.parser.xlrd.open_workbook", return_value=workbook) as opener:
            self.assertEqual(_read_legacy_xls(_CFB_SIGNATURE), ())

        kwargs = opener.call_args.kwargs
        self.assertEqual(kwargs["file_contents"], _CFB_SIGNATURE)
        self.assertTrue(kwargs["formatting_info"])
        self.assertTrue(kwargs["on_demand"])
        self.assertFalse(kwargs["ignore_workbook_corruption"])
        self.assertTrue(hasattr(kwargs["logfile"], "write"))
        workbook.release_resources.assert_called_once_with()

    def test_biff_formula_scanner_finds_formula_coordinates(self):
        formula_data = pack("<HH", 9, 3) + b"\x00" * 18
        stream = (
            pack("<HH", 0x0809, 0)
            + pack("<HH", XL_FORMULA, len(formula_data))
            + formula_data
            + pack("<HH", XL_EOF, 0)
        )
        workbook = SimpleNamespace(
            mem=stream,
            base=0,
            stream_len=len(stream),
            _sh_abs_posn=[0],
        )

        self.assertEqual(_formula_coordinates(workbook, 0), frozenset({(9, 3)}))

    def test_provenance_identifies_artifact_sheet_row_columns_and_types(self):
        record = self.parse_sheet().parsed_records[0]
        provenance = record.provenance

        self.assertEqual(provenance["artifact_identity"], "synthetic-artifact")
        self.assertEqual(provenance["source_variant"], "bci_current_cartola_xls")
        self.assertEqual(provenance["contract_version"], "bci_current_cartola_v0.1")
        self.assertEqual(provenance["worksheet_ordinal"], 1)
        self.assertEqual(provenance["row_number"], 10)
        self.assertEqual(provenance["source_fields"]["source_series"]["coordinate"], "C10")
        self.assertEqual(provenance["source_fields"]["source_signed_amount"]["cell_type"], "text")

    def test_repeated_parsing_is_deterministic(self):
        sheet = synthetic_current_cartola_sheet()

        self.assertEqual(self.parse_sheet(sheet), self.parse_sheet(sheet))

    def test_private_values_are_absent_from_public_representations(self):
        marker = "PRIVATE_STYLE_MARKER_41820"
        sheet = synthetic_current_cartola_sheet(
            transactions=[{"date": "25-08-2031", "description": marker, "series": marker, "amount": "9.876", "balance": "1"}]
        )
        result = self.parse_sheet(sheet)
        rendered = repr(result) + repr(result.parsed_records[0]) + repr(result.parsed_records[0].raw_cells["B"])

        self.assertNotIn(marker, rendered)
        self.assertNotIn("9.876", rendered)


if __name__ == "__main__":
    unittest.main()
