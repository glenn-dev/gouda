from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from gouda.ledger.models import ImportBatch
from gouda.ledger.services.santander_import import (
    PARSER_ERROR_UNRECOGNIZED,
    PARSER_RESULT_GRAPH_INVALID,
    PARSER_UNEXPECTED,
    SANTANDER_SOURCE_VARIANT_V1,
    SOURCE_VARIANT_UNSUPPORTED,
    SantanderImportValidationError,
    assert_santander_v1_structure,
    derive_batch_status,
    map_parser_failure_code,
    recognize_santander_v1,
    serialize_santander_raw_cells,
    validate_movement_money,
    validate_reconciliation_money,
    validate_santander_parser_result,
)
from gouda.santander_parser import (
    PARSER_VERSION,
    AmbiguousWorksheetError,
    MalformedWorkbookError,
    ParseResult,
    ParserError,
    ReconciliationStatus,
    RowOutcome,
    SourceCell,
    UnsupportedWorkbookError,
    parse_workbook,
)
from tests.test_santander_parser import workbook_bytes


ACCOUNT_REF = "synthetic-account-ref"
CURRENCY = "ZZZ"


class RawCellSerializerTests(SimpleTestCase):
    def test_serializes_every_supported_type_with_explicit_tags_and_metadata(self):
        moment = datetime(2026, 2, 4, 5, 6, 7, 8, tzinfo=timezone.utc)
        raw_cells = {
            "H": SourceCell(moment, cell_type="d", number_format="yyyy-mm-dd hh:mm:ss", is_date=True),
            "G": SourceCell(date(2026, 2, 4), cell_type="d", number_format="yyyy-mm-dd", is_date=True),
            "F": SourceCell(1.5, cell_type="n", number_format="0.0"),
            "E": SourceCell(Decimal("1234.50"), cell_type="n", number_format="0.00"),
            "D": SourceCell("Synthetic", cell_type="s", number_format="General"),
            "C": SourceCell(-42, cell_type="n", number_format="0"),
            "B": SourceCell(True, cell_type="b", number_format="General"),
            "A": SourceCell(None, cell_type="n", number_format="General", is_formula=False),
        }

        serialized = serialize_santander_raw_cells(raw_cells)

        self.assertEqual(serialized["schema"], "santander-source-row-v1")
        self.assertEqual([cell["column"] for cell in serialized["cells"]], list("ABCDEFGH"))
        values = [cell["value"] for cell in serialized["cells"]]
        self.assertEqual(values[0], {"type": "null"})
        self.assertEqual(values[1], {"type": "boolean", "value": True})
        self.assertEqual(values[2], {"type": "integer", "text": "-42"})
        self.assertEqual(values[3], {"type": "string", "text": "Synthetic"})
        self.assertEqual(values[4], {"type": "decimal", "text": "1234.50"})
        self.assertEqual(values[5], {"type": "float", "hex": (1.5).hex()})
        self.assertEqual(values[6], {"type": "date", "text": "2026-02-04"})
        self.assertEqual(values[7], {"type": "datetime", "text": "2026-02-04T05:06:07.000008+00:00"})
        self.assertEqual(serialized["cells"][7]["cell_type"], "d")
        self.assertEqual(serialized["cells"][7]["number_format"], "yyyy-mm-dd hh:mm:ss")
        self.assertTrue(serialized["cells"][7]["is_date"])
        self.assertFalse(serialized["cells"][7]["is_formula"])

    def test_bool_precedes_int_and_datetime_precedes_date(self):
        serialized = serialize_santander_raw_cells(
            {
                "A": SourceCell(True),
                "B": SourceCell(datetime(2026, 1, 1)),
            }
        )
        self.assertEqual(serialized["cells"][0]["value"]["type"], "boolean")
        self.assertEqual(serialized["cells"][1]["value"]["type"], "datetime")

    def test_formula_and_cell_metadata_are_preserved(self):
        serialized = serialize_santander_raw_cells(
            {"A": SourceCell("=1+1", cell_type="f", number_format="0.00", is_formula=True)}
        )
        cell = serialized["cells"][0]
        self.assertEqual(cell["cell_type"], "f")
        self.assertEqual(cell["number_format"], "0.00")
        self.assertTrue(cell["is_formula"])

    def test_serialization_is_deterministic(self):
        cells = {"C": SourceCell(3), "A": SourceCell(1), "B": SourceCell(2)}
        self.assertEqual(serialize_santander_raw_cells(cells), serialize_santander_raw_cells(cells))

    def test_rejects_nonfinite_numeric_values(self):
        for value in (float("nan"), float("inf"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=type(value).__name__), self.assertRaises(SantanderImportValidationError):
                serialize_santander_raw_cells({"A": SourceCell(value)})

    def test_rejects_unsupported_values_and_invalid_metadata(self):
        invalid_cells = (
            {"A": SourceCell(object())},
            {"A": object()},
            {"A": SourceCell("value", cell_type=1)},
            {"A": SourceCell("value", number_format=1)},
            {"A": SourceCell("value", is_date=1)},
        )
        for cells in invalid_cells:
            with self.subTest(cells=tuple(cells)), self.assertRaises(SantanderImportValidationError):
                serialize_santander_raw_cells(cells)

    def test_rejects_nul_and_invalid_unicode(self):
        for value in ("unsafe\x00value", "unsafe\ud800value"):
            with self.subTest(repr=ascii(value)), self.assertRaises(SantanderImportValidationError):
                serialize_santander_raw_cells({"A": SourceCell(value)})


class BatchStatusTests(SimpleTestCase):
    def test_derives_status_independently_of_ignored_rows(self):
        cases = (
            (0, 0, ImportBatch.Status.ACCEPTED),
            (3, 0, ImportBatch.Status.ACCEPTED),
            (3, 2, ImportBatch.Status.PARTIAL),
            (0, 2, ImportBatch.Status.REJECTED),
        )
        for parsed_count, rejected_count, expected in cases:
            with self.subTest(parsed=parsed_count, rejected=rejected_count):
                self.assertEqual(
                    derive_batch_status(parsed_count=parsed_count, rejected_count=rejected_count),
                    expected,
                )

    def test_rejects_invalid_counts(self):
        for counts in ((-1, 0), (0, -1), (True, 0)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                derive_batch_status(parsed_count=counts[0], rejected_count=counts[1])


class ParserErrorMappingTests(SimpleTestCase):
    def test_maps_every_known_parser_failure(self):
        failures = (
            (MalformedWorkbookError("xlsx_invalid"), "xlsx_invalid"),
            (UnsupportedWorkbookError("movement_header_not_found"), "movement_header_not_found"),
            (AmbiguousWorksheetError("ambiguous_statement_worksheets"), "ambiguous_statement_worksheets"),
            (UnsupportedWorkbookError("formula_unsupported"), "formula_unsupported"),
            (UnsupportedWorkbookError("period_context_missing"), "period_context_missing"),
            (UnsupportedWorkbookError("period_context_ambiguous"), "period_context_ambiguous"),
            (UnsupportedWorkbookError("period_context_invalid"), "period_context_invalid"),
        )
        for error, expected in failures:
            with self.subTest(expected=expected):
                self.assertEqual(map_parser_failure_code(error), expected)

    def test_unknown_parser_codes_and_nonparser_failures_are_sanitized(self):
        self.assertEqual(map_parser_failure_code(ParserError("private-value")), PARSER_ERROR_UNRECOGNIZED)
        self.assertEqual(map_parser_failure_code(RuntimeError("private-value")), PARSER_UNEXPECTED)


class MoneyBoundaryTests(SimpleTestCase):
    def test_accepts_exact_movement_and_reconciliation_money(self):
        validate_movement_money(signed_amount=Decimal("-10.00"), running_balance=Decimal("90.00"))
        validate_reconciliation_money(
            opening_balance=Decimal("100.00"),
            ending_balance=Decimal("90.00"),
            difference=Decimal("0.00"),
        )

    def test_rejects_zero_movement(self):
        with self.assertRaises(ValidationError) as context:
            validate_movement_money(signed_amount=Decimal("0.00"), running_balance=None)
        self.assertEqual(context.exception.code, "movement_amount_zero")

    def test_reuses_exact_money_validation_codes(self):
        cases = (
            (1, "money_not_finite"),
            (Decimal("1.001"), "money_scale_exceeded"),
            (Decimal("1000000000000000000.00"), "money_precision_exceeded"),
            (Decimal("NaN"), "money_not_finite"),
        )
        for value, expected_code in cases:
            with self.subTest(expected_code=expected_code), self.assertRaises(ValidationError) as context:
                validate_movement_money(signed_amount=value, running_balance=None)
            self.assertEqual(context.exception.code, expected_code)

    def test_validates_optional_running_and_reconciliation_values(self):
        with self.assertRaises(ValidationError) as running_context:
            validate_movement_money(signed_amount=Decimal("1.00"), running_balance=Decimal("1.001"))
        self.assertEqual(running_context.exception.code, "money_scale_exceeded")

        with self.assertRaises(ValidationError) as reconciliation_context:
            validate_reconciliation_money(
                opening_balance=Decimal("1.00"),
                ending_balance=Decimal("1000000000000000000.00"),
                difference=None,
            )
        self.assertEqual(reconciliation_context.exception.code, "money_precision_exceeded")


class SantanderResultValidationTests(SimpleTestCase):
    def parse(self, *, rows=None, opening="$10", ending="$9") -> ParseResult:
        return parse_workbook(
            workbook_bytes(
                opening=opening,
                ending=ending,
                rows=rows or [["04/02", "cargo", "Synthetic", "REF", "$1", None, "$9"]],
            ),
            currency=CURRENCY,
            account_ref=ACCOUNT_REF,
        )

    def assert_graph_invalid(self, result: ParseResult) -> None:
        with self.assertRaises(SantanderImportValidationError) as context:
            validate_santander_parser_result(
                result,
                expected_account_ref=ACCOUNT_REF,
                expected_currency=CURRENCY,
            )
        self.assertEqual(context.exception.code, PARSER_RESULT_GRAPH_INVALID)

    def replace_row(self, result: ParseResult, index: int, row) -> ParseResult:
        rows = list(result.rows)
        rows[index] = row
        return replace(result, rows=tuple(rows))

    def parsed_row_index(self, result: ParseResult) -> int:
        return next(index for index, row in enumerate(result.rows) if row.outcome is RowOutcome.PARSED)

    def test_valid_result_and_marker_free_v1_are_accepted(self):
        result = self.parse()
        validate_santander_parser_result(
            result,
            expected_account_ref=ACCOUNT_REF,
            expected_currency=CURRENCY,
        )
        self.assertEqual(
            recognize_santander_v1(
                result,
                expected_account_ref=ACCOUNT_REF,
                expected_currency=CURRENCY,
            ),
            SANTANDER_SOURCE_VARIANT_V1,
        )

    def test_wrong_result_shape_and_movement_text_type_are_rejected(self):
        with self.assertRaises(SantanderImportValidationError) as context:
            validate_santander_parser_result(
                object(),
                expected_account_ref=ACCOUNT_REF,
                expected_currency=CURRENCY,
            )
        self.assertEqual(context.exception.code, PARSER_RESULT_GRAPH_INVALID)

        result = self.parse()
        index = self.parsed_row_index(result)
        row = result.rows[index]
        wrong_text = replace(row.movement, description=123)
        self.assert_graph_invalid(self.replace_row(result, index, replace(row, movement=wrong_text)))

    def test_missing_and_extra_movements_are_rejected(self):
        result = self.parse()
        parsed_index = self.parsed_row_index(result)
        missing = self.replace_row(
            result,
            parsed_index,
            replace(result.rows[parsed_index], movement=None),
        )
        self.assert_graph_invalid(missing)

        ignored_index = next(index for index, row in enumerate(result.rows) if row.outcome is RowOutcome.IGNORED)
        extra = replace(result.rows[ignored_index], movement=result.rows[parsed_index].movement)
        self.assert_graph_invalid(self.replace_row(result, ignored_index, extra))

    def test_wrong_and_duplicate_source_record_links_are_rejected(self):
        result = self.parse(
            rows=[
                ["04/02", "cargo", "Synthetic one", "REF-1", "$1", None, "$9"],
                ["05/02", "cargo", "Synthetic two", "REF-2", "$1", None, "$8"],
            ],
            ending="$8",
        )
        parsed_indexes = [index for index, row in enumerate(result.rows) if row.outcome is RowOutcome.PARSED]
        first, second = (result.rows[index] for index in parsed_indexes)
        wrong_movement = replace(second.movement, source_record_id=first.raw_record.raw_record_id)
        wrong_link = self.replace_row(
            result,
            parsed_indexes[1],
            replace(second, movement=wrong_movement),
        )
        self.assert_graph_invalid(wrong_link)

    def test_invalid_row_sequence_and_parser_code_are_rejected(self):
        result = self.parse()
        row = result.rows[0]
        wrong_number = replace(row.raw_record, row_number=2, raw_record_id="S1:row:2")
        self.assert_graph_invalid(self.replace_row(result, 0, replace(row, raw_record=wrong_number)))

        wrong_code = replace(row, error_codes=("unknown_private_code",))
        self.assert_graph_invalid(self.replace_row(result, 0, wrong_code))

    def test_wrong_worksheet_provenance_is_rejected(self):
        result = self.parse()
        row = result.rows[0]
        wrong_raw = replace(row.raw_record, worksheet_ordinal=2)
        self.assert_graph_invalid(self.replace_row(result, 0, replace(row, raw_record=wrong_raw)))

    def test_wrong_reported_counts_are_rejected(self):
        result = self.parse()

        class WrongCountResult(ParseResult):
            @property
            def parsed_count(self):
                return super().parsed_count + 1

        wrong = WrongCountResult(
            result.sheet_alias,
            result.worksheet_name,
            result.worksheet_ordinal,
            result.period_start,
            result.period_end,
            result.rows,
            result.reconciliation,
        )
        self.assert_graph_invalid(wrong)

    def test_wrong_account_currency_and_source_columns_are_rejected(self):
        result = self.parse()
        index = self.parsed_row_index(result)
        row = result.rows[index]
        mutations = (
            replace(row.movement, account_ref="wrong-account"),
            replace(row.movement, currency="USD"),
            replace(row.movement, provenance={**row.movement.provenance, "source_columns": ("A", "F")}),
        )
        for movement in mutations:
            with self.subTest(movement=movement.source_record_id):
                self.assert_graph_invalid(self.replace_row(result, index, replace(row, movement=movement)))

    def test_out_of_period_date_and_wrong_provenance_are_rejected(self):
        result = self.parse()
        index = self.parsed_row_index(result)
        row = result.rows[index]
        out_of_period = replace(row.movement, occurrence_date=result.period_end + timedelta(days=1))
        wrong_provenance = replace(
            row.movement,
            provenance={**row.movement.provenance, "parser_version": "wrong-version"},
        )
        self.assert_graph_invalid(self.replace_row(result, index, replace(row, movement=out_of_period)))
        self.assert_graph_invalid(self.replace_row(result, index, replace(row, movement=wrong_provenance)))

    def test_wrong_expected_parser_version_is_rejected(self):
        result = self.parse()
        with self.assertRaises(SantanderImportValidationError) as context:
            validate_santander_parser_result(
                result,
                expected_account_ref=ACCOUNT_REF,
                expected_currency=CURRENCY,
                expected_parser_version="wrong-version",
            )
        self.assertEqual(context.exception.code, PARSER_RESULT_GRAPH_INVALID)
        self.assertTrue(PARSER_VERSION)

    def test_reconciliation_mismatch_and_invalid_state_are_rejected(self):
        result = self.parse()
        wrong_difference = replace(
            result,
            reconciliation=replace(
                result.reconciliation,
                difference=result.reconciliation.difference + Decimal("1"),
            ),
        )
        invalid_state = replace(
            result,
            reconciliation=replace(
                result.reconciliation,
                status=ReconciliationStatus.INSUFFICIENT_DATA,
            ),
        )
        self.assert_graph_invalid(wrong_difference)
        self.assert_graph_invalid(invalid_state)

    def test_insufficient_and_not_applicable_reconciliation_are_valid(self):
        insufficient = self.parse(opening=None, ending=None)
        validate_santander_parser_result(
            insufficient,
            expected_account_ref=ACCOUNT_REF,
            expected_currency=CURRENCY,
        )
        self.assertEqual(insufficient.reconciliation.status, ReconciliationStatus.INSUFFICIENT_DATA)

        not_applicable = self.parse(
            rows=[["Synthetic note", None, None, None, None, None, None]],
            opening="$10",
            ending="$10",
        )
        validate_santander_parser_result(
            not_applicable,
            expected_account_ref=ACCOUNT_REF,
            expected_currency=CURRENCY,
        )
        self.assertEqual(not_applicable.reconciliation.status, ReconciliationStatus.NOT_APPLICABLE)

    def test_populated_column_beyond_g_is_not_v1(self):
        result = self.parse()
        row = result.rows[0]
        raw = replace(row.raw_record, raw_cells={**row.raw_record.raw_cells, "H": SourceCell("unsafe")})
        changed = self.replace_row(result, 0, replace(row, raw_record=raw))
        validate_santander_parser_result(
            changed,
            expected_account_ref=ACCOUNT_REF,
            expected_currency=CURRENCY,
        )
        with self.assertRaises(SantanderImportValidationError) as context:
            assert_santander_v1_structure(changed)
        self.assertEqual(context.exception.code, SOURCE_VARIANT_UNSUPPORTED)

    def test_known_optional_section_markers_present_in_valid_order_are_accepted(self):
        result = self.parse(
            rows=[
                ["04/02", "cargo", "Primary synthetic", "PRIMARY", "$1", None, "$9"],
                [None, None, "Resumen de Comisiones", None, None, None, None],
                ["04/02", "cargo", "Summary synthetic", "SUMMARY", "$1", None, "$9"],
                ["MENSAJES", None, None, None, None, None, None],
            ],
        )
        self.assertEqual(
            recognize_santander_v1(
                result,
                expected_account_ref=ACCOUNT_REF,
                expected_currency=CURRENCY,
            ),
            SANTANDER_SOURCE_VARIANT_V1,
        )

    def test_changed_dangerous_section_layout_is_not_v1(self):
        result = self.parse(
            rows=[
                ["04/02", "cargo", "Primary synthetic", "PRIMARY", "$1", None, "$9"],
                [None, None, "Resumen de Tarifas", None, None, None, None],
                ["04/02", "cargo", "Summary synthetic", "SUMMARY", "$1", None, "$9"],
                ["MENSAJES", None, None, None, None, None, None],
            ],
        )
        validate_santander_parser_result(
            result,
            expected_account_ref=ACCOUNT_REF,
            expected_currency=CURRENCY,
        )
        with self.assertRaises(SantanderImportValidationError) as context:
            assert_santander_v1_structure(result)
        self.assertEqual(context.exception.code, SOURCE_VARIANT_UNSUPPORTED)

    def test_changed_header_semantics_are_not_v1(self):
        result = self.parse()
        header_index = next(index for index, row in enumerate(result.rows) if "header_row" in row.error_codes)
        row = result.rows[header_index]
        cells = dict(row.raw_record.raw_cells)
        cells["C"] = replace(cells["C"], value="Unknown field")
        changed_raw = replace(row.raw_record, raw_cells=cells)
        changed = self.replace_row(result, header_index, replace(row, raw_record=changed_raw))
        with self.assertRaises(SantanderImportValidationError) as context:
            assert_santander_v1_structure(changed)
        self.assertEqual(context.exception.code, SOURCE_VARIANT_UNSUPPORTED)
