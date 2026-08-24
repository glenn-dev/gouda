from __future__ import annotations

import hashlib
from io import BytesIO
import logging
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from gouda.ledger.models import Account, ImportBatch, Movement, RawRecord, SourceArtifact
from gouda.ledger.services import santander_import as service
from gouda.santander_parser import (
    PARSER_VERSION,
    AmbiguousWorksheetError,
    MalformedWorkbookError,
    ParserError,
    UnsupportedWorkbookError,
    parse_workbook,
)
from tests.test_santander_parser import workbook_bytes


class SantanderImportServiceTests(TransactionTestCase):
    def setUp(self):
        self.account = Account.objects.create(
            display_name="Synthetic current account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        self.content = workbook_bytes(
            opening="$10.00",
            ending="$11.00",
            rows=[
                ["04/02", "cargo", "Synthetic debit", "SYN-D", "$1.00", None, "$9.00"],
                ["05/02", "abono", "Synthetic credit", "SYN-C", None, "$2.00", "$11.00"],
            ],
        )

    def import_content(self, *, content=None, filename="synthetic-statement.xlsx", account=None):
        return service.import_santander_current_account_xlsx(
            content=self.content if content is None else content,
            original_filename=filename,
            account=self.account if account is None else account,
        )

    def assert_fatal(self, batch, *, stage, code, variant=None):
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.FATAL)
        self.assertEqual(batch.failure_stage, stage)
        self.assertEqual(batch.failure_code, code)
        self.assertEqual(batch.source_variant, variant)
        self.assertIsNotNone(batch.completed_at)
        self.assertEqual((batch.parsed_count, batch.ignored_count, batch.rejected_count), (0, 0, 0))
        self.assertIsNone(batch.reconciliation_status)
        self.assertFalse(batch.raw_records.exists())
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=batch).exists())

    def test_happy_path_materializes_complete_exact_graph_outside_transactions(self):
        real_parse = service.parse_workbook

        def assert_outside_transaction(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            return real_parse(*args, **kwargs)

        with patch.object(service, "parse_workbook", side_effect=assert_outside_transaction) as parser:
            batch = self.import_content(filename=" /incoming/synthetic-statement.xlsx ")

        expected = parse_workbook(
            self.content,
            currency=self.account.currency,
            account_ref=str(self.account.pk),
        )
        artifact = batch.source_artifact
        self.assertEqual(bytes(artifact.content), self.content)
        self.assertEqual(artifact.original_filename, "synthetic-statement.xlsx")
        self.assertEqual(artifact.content_digest, hashlib.sha256(self.content).hexdigest())
        self.assertEqual(artifact.source_kind, SourceArtifact.SourceKind.SANTANDER_CURRENT_ACCOUNT_XLSX)
        self.assertEqual(batch.parser_version, PARSER_VERSION)
        self.assertEqual(batch.source_variant, service.SANTANDER_SOURCE_VARIANT_V1)
        self.assertEqual(batch.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(batch.reconciliation_status, ImportBatch.ReconciliationStatus.RECONCILED)
        self.assertEqual(
            (batch.parsed_count, batch.ignored_count, batch.rejected_count),
            (expected.parsed_count, expected.ignored_count, expected.rejected_count),
        )
        self.assertEqual(
            (batch.sheet_alias, batch.worksheet_name, batch.worksheet_ordinal),
            (expected.sheet_alias, expected.worksheet_name, expected.worksheet_ordinal),
        )
        self.assertEqual((batch.period_start, batch.period_end), (expected.period_start, expected.period_end))
        self.assertEqual(
            (batch.opening_balance, batch.ending_balance, batch.reconciliation_difference),
            (
                expected.reconciliation.opening_balance,
                expected.reconciliation.ending_balance,
                expected.reconciliation.difference,
            ),
        )
        raws = list(batch.raw_records.order_by("row_number"))
        self.assertEqual(len(raws), len(expected.rows))
        self.assertEqual([raw.row_number for raw in raws], list(range(1, len(expected.rows) + 1)))
        self.assertTrue(all(raw.raw_cells["schema"] == "santander-source-row-v1" for raw in raws))
        parsed_raws = [raw for raw in raws if raw.parse_outcome == RawRecord.ParseOutcome.PARSED]
        nonparsed_raws = [raw for raw in raws if raw.parse_outcome != RawRecord.ParseOutcome.PARSED]
        self.assertEqual(Movement.objects.filter(raw_record__in=parsed_raws).count(), expected.parsed_count)
        self.assertFalse(Movement.objects.filter(raw_record__in=nonparsed_raws).exists())
        movements = list(Movement.objects.filter(raw_record__import_batch=batch).order_by("occurrence_date"))
        self.assertEqual(
            [movement.signed_amount for movement in movements],
            [movement.signed_amount for movement in expected.parsed_movements],
        )
        self.assertEqual([movement.currency for movement in movements], [self.account.currency] * len(movements))
        parser.assert_called_once_with(
            self.content,
            currency=self.account.currency,
            account_ref=str(self.account.pk),
        )

    def test_refetched_account_context_overrides_mutable_caller_fields(self):
        self.account.currency = "USD"
        batch = self.import_content()
        self.assertEqual(batch.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(
            set(Movement.objects.filter(raw_record__import_batch=batch).values_list("currency", flat=True)),
            {"ZZZ"},
        )

    def test_sequential_duplicate_skips_parser_and_has_no_canonical_rows(self):
        canonical = self.import_content()
        canonical_raw_ids = set(canonical.raw_records.values_list("pk", flat=True))
        canonical_movement_ids = set(
            Movement.objects.filter(raw_record__import_batch=canonical).values_list("pk", flat=True)
        )

        with patch.object(service, "parse_workbook") as parser:
            duplicate = self.import_content(filename="later-name.xlsx")

        parser.assert_not_called()
        self.assertEqual(duplicate.status, ImportBatch.Status.DUPLICATE)
        self.assertEqual(duplicate.duplicate_of_id, canonical.pk)
        self.assertEqual(duplicate.parser_version, PARSER_VERSION)
        self.assertEqual(duplicate.source_variant, canonical.source_variant)
        self.assertIsNotNone(duplicate.started_at)
        self.assertIsNotNone(duplicate.completed_at)
        self.assertGreaterEqual(duplicate.completed_at, duplicate.started_at)
        self.assertEqual((duplicate.parsed_count, duplicate.ignored_count, duplicate.rejected_count), (0, 0, 0))
        self.assertIsNone(duplicate.sheet_alias)
        self.assertIsNone(duplicate.period_start)
        self.assertIsNone(duplicate.reconciliation_status)
        self.assertIsNone(duplicate.failure_code)
        self.assertFalse(duplicate.raw_records.exists())
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=duplicate).exists())
        self.assertEqual(
            set(canonical.raw_records.values_list("pk", flat=True)),
            canonical_raw_ids,
        )
        self.assertEqual(
            set(Movement.objects.filter(raw_record__import_batch=canonical).values_list("pk", flat=True)),
            canonical_movement_ids,
        )
        self.assertEqual(
            ImportBatch.objects.filter(
                source_artifact=canonical.source_artifact,
                account=self.account,
                status__in=(
                    ImportBatch.Status.ACCEPTED,
                    ImportBatch.Status.PARTIAL,
                    ImportBatch.Status.REJECTED,
                ),
            ).count(),
            1,
        )

    def test_same_artifact_materializes_independently_for_another_account(self):
        first = self.import_content()
        other = Account.objects.create(
            display_name="Other synthetic current account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        second = self.import_content(account=other)

        self.assertEqual(first.source_artifact_id, second.source_artifact_id)
        self.assertEqual(SourceArtifact.objects.count(), 1)
        self.assertEqual(first.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(second.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(
            ImportBatch.objects.filter(status__in=(ImportBatch.Status.ACCEPTED,)).count(),
            2,
        )

    def test_partial_rejected_and_all_ignored_results_materialize_canonically(self):
        cases = (
            (
                workbook_bytes(rows=[
                    ["04/02", "cargo", "Synthetic valid", "SYN-V", "$1", None, "$9"],
                    ["05/02", "cargo", "Synthetic conflict", "SYN-X", "$1", "$1", "$9"],
                ], opening="$10", ending="$9"),
                ImportBatch.Status.PARTIAL,
                1,
            ),
            (
                workbook_bytes(rows=[
                    ["05/02", "cargo", "Synthetic conflict", "SYN-X", "$1", "$1", "$9"],
                ]),
                ImportBatch.Status.REJECTED,
                0,
            ),
            (
                workbook_bytes(rows=[
                    ["Synthetic note", None, None, None, None, None, None],
                ]),
                ImportBatch.Status.ACCEPTED,
                0,
            ),
        )
        for index, (content, expected_status, movement_count) in enumerate(cases):
            account = Account.objects.create(
                display_name=f"Synthetic status account {index}",
                kind=Account.Kind.CURRENT,
                economic_orientation=Account.EconomicOrientation.ASSET,
                currency="ZZZ",
            )
            with self.subTest(status=expected_status):
                batch = self.import_content(content=content, account=account)
                self.assertEqual(batch.status, expected_status)
                self.assertEqual(
                    Movement.objects.filter(raw_record__import_batch=batch).count(),
                    movement_count,
                )
        all_ignored = ImportBatch.objects.get(account=account)
        self.assertEqual(all_ignored.reconciliation_status, ImportBatch.ReconciliationStatus.NOT_APPLICABLE)

    def test_post_parse_duplicate_path_finalizes_directly_to_materialized_target(self):
        real_parse = service.parse_workbook
        target_id = None

        def create_winner(*args, **kwargs):
            nonlocal target_id
            artifact = SourceArtifact.objects.get()
            target = ImportBatch.objects.create(
                source_artifact=artifact,
                account=self.account,
                parser_version=PARSER_VERSION,
                source_variant=service.SANTANDER_SOURCE_VARIANT_V1,
                status=ImportBatch.Status.ACCEPTED,
                completed_at=timezone.now(),
                reconciliation_status=ImportBatch.ReconciliationStatus.NOT_APPLICABLE,
            )
            target_id = target.pk
            return real_parse(*args, **kwargs)

        with patch.object(service, "parse_workbook", side_effect=create_winner):
            duplicate = self.import_content()

        self.assertEqual(duplicate.status, ImportBatch.Status.DUPLICATE)
        self.assertEqual(duplicate.duplicate_of_id, target_id)
        self.assertEqual(duplicate.source_variant, service.SANTANDER_SOURCE_VARIANT_V1)
        self.assertFalse(duplicate.raw_records.exists())
        self.assertFalse(Movement.objects.filter(raw_record__import_batch=duplicate).exists())

    def test_fatal_attempt_does_not_block_later_success(self):
        with patch.object(service, "parse_workbook", side_effect=MalformedWorkbookError("xlsx_invalid")):
            fatal = self.import_content()
        successful = self.import_content()

        self.assert_fatal(fatal, stage=ImportBatch.FailureStage.PARSER, code="xlsx_invalid")
        self.assertEqual(successful.status, ImportBatch.Status.ACCEPTED)
        self.assertEqual(fatal.source_artifact_id, successful.source_artifact_id)

    def test_parser_failures_are_whitelisted_and_durable(self):
        failures = (
            (MalformedWorkbookError("xlsx_invalid"), "xlsx_invalid"),
            (UnsupportedWorkbookError("movement_header_not_found"), "movement_header_not_found"),
            (AmbiguousWorksheetError("ambiguous_statement_worksheets"), "ambiguous_statement_worksheets"),
            (UnsupportedWorkbookError("formula_unsupported"), "formula_unsupported"),
            (UnsupportedWorkbookError("period_context_missing"), "period_context_missing"),
            (UnsupportedWorkbookError("period_context_ambiguous"), "period_context_ambiguous"),
            (UnsupportedWorkbookError("period_context_invalid"), "period_context_invalid"),
            (ParserError("SYNTHETIC_PRIVATE_CODE"), service.PARSER_ERROR_UNRECOGNIZED),
        )
        for error, expected_code in failures:
            with self.subTest(expected_code=expected_code), patch.object(
                service, "parse_workbook", side_effect=error
            ):
                batch = self.import_content()
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.PARSER,
                    code=expected_code,
                )
        self.assertEqual(SourceArtifact.objects.count(), 1)

    def test_unexpected_parser_failure_is_sanitized(self):
        sentinel = "SYNTHETIC_UNDERLYING_EXCEPTION_SECRET"
        with patch.object(service, "parse_workbook", side_effect=RuntimeError(sentinel)):
            batch = self.import_content(filename="SYNTHETIC_PRIVATE_FILENAME.xlsx")
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.PARSER,
            code=service.PARSER_UNEXPECTED,
        )
        self.assertNotIn(sentinel, batch.failure_code)

    def test_boundary_failures_are_safe_and_atomic(self):
        cases = (
            (
                "validate_santander_parser_result",
                service.SantanderImportValidationError(service.PARSER_RESULT_GRAPH_INVALID),
                service.PARSER_RESULT_GRAPH_INVALID,
                None,
            ),
            (
                "assert_santander_v1_structure",
                service.SantanderImportValidationError(service.SOURCE_VARIANT_UNSUPPORTED),
                service.SOURCE_VARIANT_UNSUPPORTED,
                None,
            ),
            (
                "validate_movement_money",
                ValidationError("synthetic", code="money_scale_exceeded"),
                "money_scale_exceeded",
                service.SANTANDER_SOURCE_VARIANT_V1,
            ),
        )
        for function_name, error, expected_code, expected_variant in cases:
            with self.subTest(code=expected_code), patch.object(service, function_name, side_effect=error):
                batch = self.import_content()
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.BOUNDARY,
                    code=expected_code,
                    variant=expected_variant,
                )

    def test_changed_account_context_is_boundary_fatal(self):
        real_parse = service.parse_workbook

        def mutate_account(*args, **kwargs):
            result = real_parse(*args, **kwargs)
            Account.objects.filter(pk=self.account.pk).update(currency="USD")
            return result

        with patch.object(service, "parse_workbook", side_effect=mutate_account):
            batch = self.import_content()
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.ACCOUNT_CONTEXT_CHANGED,
            variant=service.SANTANDER_SOURCE_VARIANT_V1,
        )

    def test_changed_account_orientation_is_boundary_fatal(self):
        real_parse = service.parse_workbook
        real_select_for_update = Account.objects.select_for_update

        def mutate_account_orientation(*args, **kwargs):
            result = real_parse(*args, **kwargs)
            locked_queryset = real_select_for_update()
            real_get = locked_queryset.get

            def get_with_changed_orientation(*get_args, **get_kwargs):
                account = real_get(*get_args, **get_kwargs)
                account.economic_orientation = Account.EconomicOrientation.LIABILITY
                return account

            locked_queryset.get = get_with_changed_orientation
            orientation_patch = patch.object(
                Account.objects,
                "select_for_update",
                return_value=locked_queryset,
            )
            orientation_patch.start()
            self.addCleanup(orientation_patch.stop)
            return result

        with patch.object(service, "parse_workbook", side_effect=mutate_account_orientation):
            batch = self.import_content()
        self.assert_fatal(
            batch,
            stage=ImportBatch.FailureStage.BOUNDARY,
            code=service.ACCOUNT_CONTEXT_CHANGED,
            variant=service.SANTANDER_SOURCE_VARIANT_V1,
        )

    def test_materialization_rolls_back_at_each_injected_seam(self):
        seams = ("_create_raw_records", "_create_movements", "_finalize_materialized_batch")
        for seam in seams:
            original = getattr(service, seam)

            def fail_after(*args, __original=original, __seam=seam, **kwargs):
                if __seam != "_finalize_materialized_batch":
                    __original(*args, **kwargs)
                raise RuntimeError("SYNTHETIC_MATERIALIZATION_SECRET")

            with self.subTest(seam=seam), patch.object(service, seam, side_effect=fail_after):
                batch = self.import_content()
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.PERSISTENCE,
                    code=service.MATERIALIZATION_FAILED,
                    variant=service.SANTANDER_SOURCE_VARIANT_V1,
                )

    def test_database_materialization_failures_use_safe_codes(self):
        failures = (
            (IntegrityError("SYNTHETIC_SQL_SECRET"), service.MATERIALIZATION_INTEGRITY_ERROR),
            (DatabaseError("SYNTHETIC_SQL_SECRET"), service.MATERIALIZATION_DATABASE_ERROR),
        )
        for error, code in failures:
            with self.subTest(code=code), patch.object(service, "_create_raw_records", side_effect=error):
                batch = self.import_content()
                self.assert_fatal(
                    batch,
                    stage=ImportBatch.FailureStage.PERSISTENCE,
                    code=code,
                    variant=service.SANTANDER_SOURCE_VARIANT_V1,
                )

    def test_compensation_failure_raises_only_sanitized_operational_error(self):
        sentinel = "SYNTHETIC_COMPENSATION_DATABASE_SECRET"
        original_save = ImportBatch.save

        def reject_fatal(instance, *args, **kwargs):
            if instance.status == ImportBatch.Status.FATAL:
                raise DatabaseError(sentinel)
            return original_save(instance, *args, **kwargs)

        with patch.object(service, "parse_workbook", side_effect=RuntimeError("parser secret")), patch.object(
            ImportBatch, "save", new=reject_fatal
        ):
            with self.assertRaises(service.SantanderImportOperationalError) as context:
                self.import_content()

        self.assertEqual(context.exception.code, "fatal_compensation_failed")
        self.assertEqual(str(context.exception), "fatal_compensation_failed")
        self.assertNotIn(sentinel, repr(context.exception))
        batch = ImportBatch.objects.get()
        self.assertEqual(batch.status, ImportBatch.Status.PROCESSING)
        self.assertFalse(batch.raw_records.exists())

    def test_filename_normalization_and_first_seen_name(self):
        batch = self.import_content(filename=" C:\\incoming\\Cafe\u0301.xlsx ")
        artifact = batch.source_artifact
        self.assertEqual(artifact.original_filename, "Caf\u00e9.xlsx")
        duplicate = self.import_content(filename="/later/different.xlsx")
        self.assertEqual(duplicate.status, ImportBatch.Status.DUPLICATE)
        artifact.refresh_from_db()
        self.assertEqual(artifact.original_filename, "Caf\u00e9.xlsx")

    def test_filename_boundaries(self):
        accepted = "x" * 250 + ".xlsx"
        self.assertEqual(len(accepted), 255)
        batch = self.import_content(content=b"not-an-xlsx", filename=accepted)
        self.assertEqual(batch.source_artifact.original_filename, accepted)

        invalid = (None, "", "   ", "/path/", ".", "..", "bad\x00.xlsx", "bad\n.xlsx", "x" * 256)
        for filename in invalid:
            with self.subTest(filename_type=type(filename).__name__):
                with self.assertRaises(service.SantanderImportServiceError) as context:
                    self.import_content(content=b"different", filename=filename)
                self.assertEqual(context.exception.code, "filename_invalid")

    def test_content_and_account_boundaries(self):
        for invalid_content in (bytearray(self.content), memoryview(self.content), BytesIO(self.content), "path.xlsx"):
            with self.subTest(content_type=type(invalid_content).__name__):
                with self.assertRaises(service.SantanderImportServiceError) as context:
                    self.import_content(content=invalid_content)
                self.assertEqual(context.exception.code, "content_type_invalid")

        unsaved = Account(
            display_name="Unsaved",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        with self.assertRaises(service.SantanderImportServiceError) as context:
            self.import_content(account=unsaved)
        self.assertEqual(context.exception.code, "account_not_persisted")

        deleted = Account.objects.create(
            display_name="Deleted",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        deleted_id = deleted.pk
        deleted.delete()
        deleted = Account(
            pk=deleted_id,
            display_name="Deleted",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        deleted._state.adding = False
        with self.assertRaises(service.SantanderImportServiceError) as context:
            self.import_content(account=deleted)
        self.assertEqual(context.exception.code, "account_not_found")

        unsupported = Account(
            display_name="Unsupported",
            kind="CREDIT",
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="ZZZ",
        )
        unsupported.pk = self.account.pk
        unsupported._state.adding = False
        with patch.object(service, "_load_account_for_registration", return_value=unsupported):
            with self.assertRaises(service.SantanderImportServiceError) as context:
                self.import_content(account=unsupported)
        self.assertEqual(context.exception.code, "account_kind_unsupported")

        invalid_currency = Account(
            pk=self.account.pk,
            display_name="Invalid context",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="zzz",
        )
        with patch.object(service, "_load_account_for_registration", return_value=invalid_currency):
            with self.assertRaises(service.SantanderImportServiceError) as context:
                self.import_content()
        self.assertEqual(context.exception.code, "account_currency_invalid")

        invalid_orientation = Account(
            pk=self.account.pk,
            display_name="Invalid orientation",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.LIABILITY,
            currency="ZZZ",
        )
        with patch.object(service, "_load_account_for_registration", return_value=invalid_orientation):
            with self.assertRaises(service.SantanderImportServiceError) as context:
                self.import_content()
        self.assertEqual(context.exception.code, "account_orientation_unsupported")

    def test_existing_artifact_is_reused_but_mismatch_and_collision_fail_closed(self):
        first = self.import_content()
        second_account = Account.objects.create(
            display_name="Second account",
            kind=Account.Kind.CURRENT,
            economic_orientation=Account.EconomicOrientation.ASSET,
            currency="ZZZ",
        )
        reused = self.import_content(account=second_account)
        self.assertEqual(reused.source_artifact_id, first.source_artifact_id)

        first.source_artifact.source_kind = "OTHER_SOURCE"
        first.source_artifact.save(update_fields=["source_kind"])
        with self.assertRaises(service.SantanderImportServiceError) as context:
                self.import_content(account=Account.objects.create(
                    display_name="Third account",
                    kind=Account.Kind.CURRENT,
                    economic_orientation=Account.EconomicOrientation.ASSET,
                    currency="ZZZ",
            ))
        self.assertEqual(context.exception.code, "artifact_source_kind_mismatch")

        collision_content = b"different synthetic artifact bytes"
        with patch.object(service, "_content_digest", return_value=first.source_artifact.content_digest):
            with self.assertRaises(service.SantanderImportServiceError) as context:
                self.import_content(
                    content=collision_content,
                    account=Account.objects.create(
                        display_name="Collision account",
                        kind=Account.Kind.CURRENT,
                        economic_orientation=Account.EconomicOrientation.ASSET,
                        currency="ZZZ",
                    ),
                )
        self.assertEqual(context.exception.code, "content_digest_collision")

    def test_call_inside_existing_transaction_fails_before_registration(self):
        with transaction.atomic(), self.assertRaises(service.SantanderImportServiceError) as context:
            self.import_content()
        self.assertEqual(context.exception.code, "transaction_context_unsupported")
        self.assertFalse(SourceArtifact.objects.exists())
        self.assertFalse(ImportBatch.objects.exists())

    def test_sensitive_values_never_reach_logs_or_safe_failure_surfaces(self):
        sentinels = (
            "SYNTHETIC_PRIVATE_FILENAME",
            "SYNTHETIC_PRIVATE_DIGEST",
            "SYNTHETIC_PRIVATE_CONTENT",
            "SYNTHETIC_PRIVATE_CELL",
            "SYNTHETIC_PRIVATE_WORKSHEET",
            "SYNTHETIC_PRIVATE_DESCRIPTION",
            "SYNTHETIC_PRIVATE_REFERENCE",
            "SYNTHETIC_PRIVATE_FINANCIAL_VALUE",
            "SYNTHETIC_PRIVATE_UNDERLYING_ERROR",
        )
        with patch.object(logging.Logger, "_log") as log_call, patch.object(
            service,
            "parse_workbook",
            side_effect=RuntimeError(sentinels[-1]),
        ):
            batch = self.import_content(
                content=sentinels[2].encode(),
                filename=f"/private/{sentinels[0]}.xlsx",
            )

        rendered = " ".join(
            (
                batch.failure_stage or "",
                batch.failure_code or "",
                str(batch),
                repr(batch),
            )
        )
        log_call.assert_not_called()
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)
