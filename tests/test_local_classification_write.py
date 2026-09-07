import secrets
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from gouda import local_classification_write as writes, local_delivery
from gouda.ledger.management.commands.runlocal import Command
from tests.fixtures.local_classification_write import BOOTSTRAP, HEADERS


class ClassificationRuntimeTests(SimpleTestCase):
    def run_mode(self, runner, **options):
        return local_delivery.run_validated_local_delivery(
            server_runner=runner, **{
                "bind_host": "127.0.0.1", "port": "8000",
                "enable_classification_writes": True,
                "classification_write_origin": writes.WRITE_ORIGIN, **options,
            },
        )

    def test_read_default_creates_no_secret_and_cannot_bootstrap_or_mutate(self):
        def run(delivery):
            self.assertIsNotNone(delivery.trusted_principal_context())
            for method, path in (("post", BOOTSTRAP), ("patch", "/api/v1/accounts/a/movements/b/classification/")):
                response = getattr(self.client, method)(path, data="{}", content_type="application/json", **HEADERS)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"code": "mutation_not_enabled"})
        with patch.object(secrets, "token_hex") as random:
            local_delivery.run_validated_local_delivery(bind_host="::1", port="8123", server_runner=run)
        random.assert_not_called()

    def test_recreation_rotates_secret_and_expires_old_runtime_and_grant(self):
        retained = []
        def first(delivery):
            runtime = writes.require_classification_write_runtime()
            token = runtime.bootstrap_capability()
            self.assertRegex(token, r"^[0-9a-f]{64}$")
            retained.extend([runtime, token, runtime.verify_capability(token)])
            self.assertNotIn(token, repr(runtime))
            self.assertNotIn(token, repr(retained[-1]))
            self.assertEqual(runtime.bootstrap_capability(), token)
        self.run_mode(first)
        self.assertIsNone(retained[0]._capability)
        def second(delivery):
            runtime = writes.require_classification_write_runtime()
            self.assertNotEqual(runtime.bootstrap_capability(), retained[1])
            for operation in (
                lambda: runtime.verify_capability(retained[1]),
                retained[0].bootstrap_capability,
                lambda: writes.validate_classification_write_grant(retained[2]),
            ):
                with self.assertRaises(writes.ClassificationWriteError) as caught:
                    operation()
                self.assertEqual(str(caught.exception), "write_capability_invalid")
        self.run_mode(second)

    def test_failure_clears_both_runtimes(self):
        def fail(delivery):
            raise RuntimeError("synthetic")
        with self.assertRaises(RuntimeError):
            self.run_mode(fail)
        self.assertIsNone(writes._active_runtime)
        with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
            local_delivery.require_active_local_delivery_runtime()

    def test_invalid_configuration_fails_before_secret_or_runner(self):
        cases = [
            {"enable_classification_writes": value} for value in (None, 1, "true", {}, False)
        ]
        cases += [{"classification_write_origin": value} for value in (
            None, "", "null", "http://localhost:5173", "http://127.0.0.1:5173/",
            "http://127.0.0.1:8000", "https://127.0.0.1:5173", "http://[::1]:5173",
        )]
        cases += [{"bind_host": "::1"}, {"port": "8001"}, {"bind_host": "0.0.0.0"},
                  {"bind_host": "192.168.1.10"}]
        for options in cases:
            with self.subTest(options=options), patch.object(secrets, "token_hex") as random:
                with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
                    self.run_mode(lambda _: self.fail("invalid startup ran"), **options)
                random.assert_not_called()
                self.assertIsNone(writes._active_runtime)

    @override_settings(DEBUG=True)
    def test_debug_write_mode_fails_before_randomness(self):
        with patch.object(secrets, "token_hex") as random:
            with self.assertRaisesMessage(local_delivery.LocalDeliveryBootstrapError, "classification_write_debug_forbidden"):
                self.run_mode(lambda _: self.fail("debug startup ran"))
            random.assert_not_called()

    def test_supported_cli_pair_and_container_topology(self):
        for host, container in (("127.0.0.1", False), ("0.0.0.0", True)):
            def run(delivery):
                self.assertEqual(delivery.bind_host, host)
                self.assertIsNotNone(writes.require_classification_write_runtime())
            with patch.object(Command, "_serve", side_effect=run):
                call_command("runlocal", host=host, trusted_container_network=container,
                             enable_classification_writes=True,
                             classification_write_origin=writes.WRITE_ORIGIN)

    def test_cli_requires_both_flags_and_rejects_duplicates_and_abbreviations(self):
        for args in (
            ["--enable-classification-writes"],
            ["--classification-write-origin", writes.WRITE_ORIGIN],
            ["--enable-classification-writes", "--enable-classification-writes"],
            ["--classification-write-origin", writes.WRITE_ORIGIN,
             "--classification-write-origin", writes.WRITE_ORIGIN],
            ["--enable-classification-w"],
            ["--host", "127.0.0.1"],
            ["--port", "8000", "--port", "8000"],
            ["--trusted-container-network", "--trusted-container-network"],
        ):
            with self.subTest(args=args), patch.object(Command, "_serve") as serve:
                with self.assertRaises(CommandError):
                    call_command("runlocal", "--host", "127.0.0.1", *args)
                serve.assert_not_called()

    def test_opaque_runtime_and_forged_grants(self):
        with self.assertRaises(TypeError):
            writes.LocalClassificationWriteRuntime(object(), issuer=object())
        def run(delivery):
            for value in (None, {}, "trusted", writes.ClassificationWriteGrant(), delivery.trusted_principal_context()):
                with self.assertRaisesMessage(writes.ClassificationWriteError, "write_capability_invalid"):
                    writes.validate_classification_write_grant(value)
        self.run_mode(run)
