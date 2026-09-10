import secrets
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from gouda import local_classification_write, local_delivery
from gouda import local_financial_import as imports
from gouda.ledger.management.commands.runlocal import Command


class FinancialImportRuntimeTests(SimpleTestCase):
    def run_mode(self, runner, **options):
        configured = {
            "bind_host": "127.0.0.1",
            "port": "8000",
            "enable_financial_imports": True,
            "financial_import_origin": imports.IMPORT_ORIGIN,
            **options,
        }
        with patch.dict(settings.DATABASES["default"], {"NAME": imports.PRIVATE_DATABASE_NAME}):
            return local_delivery.run_validated_local_delivery(
                server_runner=runner,
                **configured,
            )

    def test_default_read_runtime_has_no_import_secret(self):
        def run(_delivery):
            with self.assertRaisesMessage(imports.FinancialImportError, "financial_import_not_enabled"):
                imports.require_financial_import_runtime()

        with patch.object(secrets, "token_hex") as random:
            local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1", port="8000", server_runner=run
            )
        random.assert_not_called()

    def test_restart_rotates_capability_and_invalidates_runtime_and_grant(self):
        retained = []

        def first(_delivery):
            runtime = imports.require_financial_import_runtime()
            token = runtime.bootstrap_capability()
            grant = runtime.verify_capability(token)
            retained.extend((runtime, token, grant))
            self.assertRegex(token, r"^[0-9a-f]{64}$")
            self.assertNotIn(token, repr(runtime))
            self.assertNotIn(token, repr(grant))

        self.run_mode(first)
        self.assertIsNone(retained[0]._capability)

        def second(_delivery):
            runtime = imports.require_financial_import_runtime()
            self.assertNotEqual(runtime.bootstrap_capability(), retained[1])
            for operation in (
                retained[0].bootstrap_capability,
                lambda: runtime.verify_capability(retained[1]),
                lambda: imports.validate_santander_current_account_import_grant(retained[2]),
            ):
                with self.assertRaisesMessage(imports.FinancialImportError, "import_capability_invalid"):
                    operation()

        self.run_mode(second)

    def test_classification_and_import_authorities_are_independent(self):
        def run(_delivery):
            classification = local_classification_write.require_classification_write_runtime()
            financial = imports.require_financial_import_runtime()
            classification_token = classification.bootstrap_capability()
            import_token = financial.bootstrap_capability()
            with self.assertRaisesMessage(imports.FinancialImportError, "import_capability_invalid"):
                financial.verify_capability(classification_token)
            with self.assertRaisesMessage(
                local_classification_write.ClassificationWriteError,
                "write_capability_invalid",
            ):
                classification.verify_capability(import_token)
            with self.assertRaisesMessage(imports.FinancialImportError, "import_capability_invalid"):
                imports.validate_santander_current_account_import_grant(
                    classification.verify_capability(classification_token)
                )
            with self.assertRaisesMessage(
                local_classification_write.ClassificationWriteError,
                "write_capability_invalid",
            ):
                local_classification_write.validate_classification_write_grant(
                    financial.verify_capability(import_token)
                )

        with patch.dict(settings.DATABASES["default"], {"NAME": imports.PRIVATE_DATABASE_NAME}):
            local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="8000",
                enable_classification_writes=True,
                classification_write_origin=local_classification_write.WRITE_ORIGIN,
                enable_financial_imports=True,
                financial_import_origin=imports.IMPORT_ORIGIN,
                server_runner=run,
            )

    def test_startup_is_fail_closed_before_randomness(self):
        cases = (
            {"enable_financial_imports": False},
            {"enable_financial_imports": None},
            {"financial_import_origin": None},
            {"financial_import_origin": "http://localhost:5173"},
            {"bind_host": "::1"},
            {"port": "8001"},
        )
        for options in cases:
            with self.subTest(options=options), patch.object(secrets, "token_hex") as random:
                with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
                    self.run_mode(lambda _: self.fail("invalid startup ran"), **options)
                random.assert_not_called()
        with patch.object(secrets, "token_hex") as random:
            with self.assertRaisesMessage(
                local_delivery.LocalDeliveryBootstrapError,
                "financial_import_dataset_invalid",
            ):
                local_delivery.run_validated_local_delivery(
                    bind_host="127.0.0.1",
                    port="8000",
                    enable_financial_imports=True,
                    financial_import_origin=imports.IMPORT_ORIGIN,
                    server_runner=lambda _: self.fail("wrong dataset ran"),
                )
            random.assert_not_called()

    @override_settings(DEBUG=True)
    def test_startup_rejects_debug_before_randomness(self):
        with patch.object(secrets, "token_hex") as random:
            with self.assertRaisesMessage(
                local_delivery.LocalDeliveryBootstrapError,
                "financial_import_debug_forbidden",
            ):
                self.run_mode(lambda _: self.fail("DEBUG startup ran"))
            random.assert_not_called()

    def test_cli_pair_and_duplicate_or_abbreviated_options(self):
        def run(_delivery):
            self.assertIsNotNone(imports.require_financial_import_runtime())

        with patch.dict(settings.DATABASES["default"], {"NAME": imports.PRIVATE_DATABASE_NAME}), patch.object(
            Command, "_serve", side_effect=run
        ):
            call_command(
                "runlocal",
                host="127.0.0.1",
                enable_financial_imports=True,
                financial_import_origin=imports.IMPORT_ORIGIN,
            )

        for args in (
            ["--enable-financial-imports"],
            ["--financial-import-origin", imports.IMPORT_ORIGIN],
            ["--enable-financial-imports", "--enable-financial-imports"],
            ["--financial-import-origin", imports.IMPORT_ORIGIN, "--financial-import-origin", imports.IMPORT_ORIGIN],
            ["--enable-financial"],
        ):
            with self.subTest(args=args), patch.object(Command, "_serve") as serve:
                with self.assertRaises(CommandError):
                    call_command("runlocal", "--host", "127.0.0.1", *args)
                serve.assert_not_called()
