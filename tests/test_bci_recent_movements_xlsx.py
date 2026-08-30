from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from gouda.bci_recent_movements_xlsx import (
    AmbiguousWorksheetError,
    MalformedWorkbookError,
    RowOutcome,
    UnsupportedWorkbookError,
    parse_bci_recent_movements_xlsx,
)
from tests.fixtures.bci_recent_movements import synthetic_recent_movements_xlsx


class BciRecentMovementsParserTests(unittest.TestCase):
    def test_valid_workbook_recognizes_exact_structure_and_source_fields(self):
        result = parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx())

        self.assertEqual(result.source_variant, "bci_recent_movements_xlsx")
        self.assertEqual(result.parser_version, "bci_recent_movements_v0.1")
        self.assertEqual(result.contract_version, "bci_recent_movements_v0.1")
        self.assertEqual((result.worksheet_name, result.worksheet_ordinal), ("movimientos", 1))
        self.assertEqual(result.parsed_count, 2)
        self.assertEqual(result.ignored_count, 8)
        self.assertEqual(result.rejected_count, 0)

        cargo, abono = result.parsed_records
        self.assertEqual(cargo.transaction_date, date(2026, 8, 25))
        self.assertEqual(cargo.accounting_date, date(2026, 8, 25))
        self.assertEqual(cargo.source_direction, "cargo")
        self.assertEqual(cargo.source_amount, Decimal("1234.00"))
        self.assertEqual(abono.source_direction, "abono")
        self.assertEqual(abono.source_amount, Decimal("2345.00"))
        self.assertFalse(hasattr(cargo, "signed_amount"))

    def test_dimension_a1_does_not_truncate_actual_rows(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                declared_dimension="A1",
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic final row",
                        "cargo": "9.999",
                    }
                ],
            )
        )

        self.assertEqual(result.actual_max_row, 9)
        self.assertEqual(result.actual_max_column, 8)
        self.assertEqual(result.parsed_count, 1)
        self.assertEqual(result.parsed_records[0].row_number, 9)

    def test_actual_iteration_reaches_final_transaction_row(self):
        rows = [
            {
                "transaction_date": f"{day:02d}/08/2026",
                "accounting_date": f"{day:02d}/08/2026",
                "description": f"Synthetic row {day}",
                "cargo": "1.000",
            }
            for day in (25, 24, 23)
        ]
        result = parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx(rows=rows))

        self.assertEqual(result.actual_max_row, 11)
        self.assertEqual(result.parsed_records[-1].row_number, 11)

    def test_cargo_and_abono_are_preserved_as_source_direction(self):
        result = parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx())

        self.assertEqual([row.source_direction for row in result.parsed_records], ["cargo", "abono"])
        self.assertEqual([row.source_amount for row in result.parsed_records], [Decimal("1234.00"), Decimal("2345.00")])

    def test_both_directional_cells_are_rejected(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic conflict",
                        "cargo": "1.000",
                        "abono": "2.000",
                    }
                ]
            )
        )

        self.assertEqual(result.parsed_count, 0)
        self.assertEqual(result.rejected_count, 1)
        self.assertEqual(result.parsed_records, ())
        self.assertEqual(result.records[-1].error_codes, ("direction_xor_invalid",))

    def test_neither_directional_cell_is_rejected(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic missing direction",
                    }
                ]
            )
        )

        self.assertEqual(result.records[-1].error_codes, ("direction_xor_invalid",))

    def test_equal_and_different_dates_are_preserved_separately(self):
        result = parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx())

        equal, different = result.parsed_records
        self.assertEqual(equal.transaction_date, equal.accounting_date)
        self.assertNotEqual(different.transaction_date, different.accounting_date)

    def test_accounting_dates_are_not_required_to_be_monotonic(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "24/08/2026",
                        "description": "Synthetic first",
                        "cargo": "1.000",
                    },
                    {
                        "transaction_date": "24/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic second",
                        "abono": "2.000",
                    },
                ]
            )
        )

        self.assertEqual(result.parsed_count, 2)

    def test_transaction_dates_must_be_newest_to_oldest(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "24/08/2026",
                        "accounting_date": "24/08/2026",
                        "description": "Synthetic first",
                        "cargo": "1.000",
                    },
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic order violation",
                        "abono": "2.000",
                    },
                ]
            )
        )

        self.assertEqual(result.records[-1].error_codes, ("transaction_date_order_invalid",))

    def test_malformed_date_is_rejected(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "31/02/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic invalid date",
                        "cargo": "1.000",
                    }
                ]
            )
        )

        self.assertIn("date_invalid", result.records[-1].error_codes)

    def test_grouping_invalid_amount_is_rejected(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic invalid amount",
                        "cargo": "12.34",
                    }
                ]
            )
        )

        self.assertEqual(result.records[-1].error_codes, ("amount_invalid",))

    def test_formula_cell_is_rejected_without_cached_value_evaluation(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "Synthetic formula",
                        "cargo": "=1+1",
                    }
                ]
            )
        )

        self.assertEqual(result.records[-1].error_codes, ("formula_unsupported",))

    def test_changed_or_missing_merge_topology_fails_closed(self):
        with self.assertRaises(UnsupportedWorkbookError) as context:
            parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx(include_merges=False))
        self.assertEqual(context.exception.code, "movement_header_not_found")

    def test_changed_header_fails_closed(self):
        with self.assertRaises(UnsupportedWorkbookError) as context:
            parse_bci_recent_movements_xlsx(
                synthetic_recent_movements_xlsx(header_overrides={"G8": "Unsupported amount"})
            )
        self.assertEqual(context.exception.code, "movement_header_not_found")

    def test_multiple_matching_worksheets_are_ambiguous(self):
        workbook = synthetic_recent_movements_xlsx(extra_sheet=True)
        with ZipFile(BytesIO(workbook)) as source:
            members = {name: source.read(name) for name in source.namelist()}
        members["xl/workbook.xml"] = members["xl/workbook.xml"].replace(
            b'name="movimientos1"', b'name="movimientos"'
        )
        workbook = BytesIO()
        with ZipFile(workbook, "w", ZIP_DEFLATED) as target:
            for name, content in members.items():
                target.writestr(name, content)

        with self.assertRaises(AmbiguousWorksheetError) as context:
            parse_bci_recent_movements_xlsx(workbook.getvalue())
        self.assertEqual(context.exception.code, "ambiguous_statement_worksheets")

    def test_unexpected_populated_region_fails_closed(self):
        workbook = synthetic_recent_movements_xlsx()
        with ZipFile(BytesIO(workbook)) as source:
            members = {name: source.read(name) for name in source.namelist()}
        sheet_name = "xl/worksheets/sheet1.xml"
        xml = members[sheet_name].replace(b"</sheetData>", b'<row r="60"><c r="J60" t="inlineStr"><is><t>unexpected</t></is></c></row></sheetData>')
        members[sheet_name] = xml
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as target:
            for name, content in members.items():
                target.writestr(name, content)

        with self.assertRaises(UnsupportedWorkbookError) as context:
            parse_bci_recent_movements_xlsx(output.getvalue())
        self.assertEqual(context.exception.code, "movement_header_not_found")

    def test_corrupt_workbook_is_typed(self):
        with self.assertRaises(MalformedWorkbookError) as context:
            parse_bci_recent_movements_xlsx(BytesIO(b"not-an-xlsx"))
        self.assertEqual(context.exception.code, "xlsx_invalid")

    def test_provenance_contains_source_identity_and_merge_membership(self):
        result = parse_bci_recent_movements_xlsx(synthetic_recent_movements_xlsx())
        provenance = result.parsed_records[0].provenance

        self.assertEqual(provenance["source_variant"], "bci_recent_movements_xlsx")
        self.assertEqual(provenance["contract_version"], "bci_recent_movements_v0.1")
        self.assertEqual(provenance["worksheet_name"], "movimientos")
        self.assertEqual(provenance["worksheet_ordinal"], 1)
        self.assertEqual(provenance["row_number"], 9)
        self.assertEqual(provenance["source_fields"]["description"]["columns"], ("C", "D", "E", "F"))
        self.assertEqual(provenance["source_fields"]["description"]["merged_range"], "C9:F9")

    def test_sensitive_values_are_absent_from_representations(self):
        result = parse_bci_recent_movements_xlsx(
            synthetic_recent_movements_xlsx(
                rows=[
                    {
                        "transaction_date": "25/08/2026",
                        "accounting_date": "25/08/2026",
                        "description": "SECRET_DESCRIPTION_908172",
                        "cargo": "9.876",
                    }
                ]
            )
        )
        rendered = repr(result) + repr(result.records[-1])

        self.assertNotIn("SECRET_DESCRIPTION_908172", rendered)
        self.assertNotIn("9.876", rendered)

    def test_repeated_parsing_is_deterministic(self):
        workbook = synthetic_recent_movements_xlsx(declared_dimension="A1")

        first = parse_bci_recent_movements_xlsx(workbook)
        second = parse_bci_recent_movements_xlsx(workbook)

        self.assertEqual(first, second)
