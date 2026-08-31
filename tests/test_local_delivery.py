from __future__ import annotations

from importlib import import_module, reload
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.core.management import CommandError, call_command
from django.core.management.commands.runserver import Command as RunserverCommand
from django.test import RequestFactory, SimpleTestCase

from gouda import local_delivery
from gouda.ledger.management.commands.runlocal import Command as RunlocalCommand


class LocalDeliveryBootstrapTests(SimpleTestCase):
    databases = set()

    def assert_bootstrap_error(self, code: str, function, /, *args, **kwargs):
        with self.assertRaises(local_delivery.LocalDeliveryBootstrapError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_exact_numeric_loopback_hosts_are_accepted(self):
        cases = (
            ("127.0.0.1", "127.0.0.1:8000", False),
            ("::1", "[::1]:8000", True),
        )

        for host, addrport, uses_ipv6 in cases:
            with self.subTest(host=host):
                def inspect(runtime):
                    self.assertIsInstance(
                        runtime,
                        local_delivery.LocalDeliveryRuntime,
                    )
                    self.assertEqual(runtime.bind_host, host)
                    self.assertEqual(runtime.port, 8000)
                    self.assertEqual(runtime.django_addrport, addrport)
                    self.assertEqual(runtime.uses_ipv6, uses_ipv6)
                    self.assertEqual(repr(runtime), "LocalDeliveryRuntime(<opaque>)")
                    self.assertIs(
                        local_delivery.require_active_local_delivery_runtime(),
                        runtime,
                    )

                local_delivery.run_validated_local_delivery(
                    bind_host=host,
                    port="8000",
                    server_runner=inspect,
                )

    def test_wildcard_routable_hostname_and_ambiguous_hosts_are_rejected(self):
        invalid_hosts = (
            "0.0.0.0",
            "::",
            "192.168.1.10",
            "10.0.0.2",
            "203.0.113.10",
            "localhost",
            "gouda.local",
            "",
            " 127.0.0.1",
            None,
        )

        for host in invalid_hosts:
            with self.subTest(host=host):
                self.assert_bootstrap_error(
                    "bind_host_invalid",
                    local_delivery.run_validated_local_delivery,
                    bind_host=host,
                    port="8000",
                    server_runner=lambda runtime: self.fail(
                        f"unsafe runtime issued: {runtime!r}"
                    ),
                )
                self.assert_bootstrap_error(
                    "local_delivery_not_active",
                    local_delivery.require_active_local_delivery_runtime,
                )

    def test_port_must_be_an_unambiguous_tcp_port(self):
        invalid_ports = (
            "",
            "0",
            "08000",
            "65536",
            "9" * 10000,
            "8000 ",
            "+8000",
            "8_000",
            "８０００",
            8000,
            None,
        )

        for port in invalid_ports:
            with self.subTest(port=port):
                self.assert_bootstrap_error(
                    "port_invalid",
                    local_delivery.run_validated_local_delivery,
                    bind_host="127.0.0.1",
                    port=port,
                    server_runner=lambda runtime: self.fail(
                        f"invalid-port runtime issued: {runtime!r}"
                    ),
                )

    def test_active_runtime_can_issue_only_the_existing_server_principal(self):
        principal = object()
        with patch(
            "gouda.ledger.services.account_access.trusted_local_principal_context",
            return_value=principal,
        ) as issuer:
            captured = []

            def issue(runtime):
                captured.append(runtime)
                return runtime.trusted_principal_context()

            result = local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="9000",
                server_runner=issue,
            )

        self.assertIs(result, principal)
        issuer.assert_called_once_with()
        self.assert_bootstrap_error(
            "local_delivery_not_active",
            captured[0].trusted_principal_context,
        )

    def test_invalid_bootstrap_cannot_issue_a_principal_or_leave_runtime_active(self):
        with patch(
            "gouda.ledger.services.account_access.trusted_local_principal_context",
        ) as issuer:
            self.assert_bootstrap_error(
                "bind_host_invalid",
                local_delivery.run_validated_local_delivery,
                bind_host="0.0.0.0",
                port="8000",
                server_runner=lambda runtime: runtime.trusted_principal_context(),
            )
            self.assert_bootstrap_error(
                "local_delivery_not_active",
                local_delivery.require_active_local_delivery_runtime,
            )

        issuer.assert_not_called()

    def test_request_and_account_values_cannot_select_bootstrap_trust(self):
        request_values = {
            "host": "127.0.0.1",
            "account_selector": uuid4(),
            "principal": "trusted-local-principal",
        }
        self.assert_bootstrap_error(
            "bind_host_invalid",
            local_delivery.run_validated_local_delivery,
            bind_host=request_values,
            port="8000",
            server_runner=lambda runtime: runtime.trusted_principal_context(),
        )

        def attempt_request_selection(runtime):
            with self.assertRaises(TypeError):
                runtime.trusted_principal_context(**request_values)

        local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=attempt_request_selection,
        )

    def test_runtime_is_nonpersistent_and_uses_no_database(self):
        # SimpleTestCase with no allowed databases fails on any query. This
        # exercises activation, lookup, and principal issuance without writes.
        def inspect(runtime):
            self.assertIs(
                local_delivery.require_active_local_delivery_runtime(),
                runtime,
            )
            self.assertIsNotNone(runtime.trusted_principal_context())

        local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=inspect,
        )

    def test_runtime_is_cleared_after_server_failure(self):
        def fail(runtime):
            raise RuntimeError("synthetic server failure")

        with self.assertRaisesRegex(RuntimeError, "synthetic server failure"):
            local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="8000",
                server_runner=fail,
            )

        self.assert_bootstrap_error(
            "local_delivery_not_active",
            local_delivery.require_active_local_delivery_runtime,
        )

    def test_nested_bootstrap_fails_closed(self):
        def start_nested(runtime):
            self.assertIs(
                local_delivery.require_active_local_delivery_runtime(),
                runtime,
            )
            self.assert_bootstrap_error(
                "local_delivery_already_active",
                local_delivery.run_validated_local_delivery,
                bind_host="::1",
                port="8001",
                server_runner=lambda nested: self.fail(
                    f"nested runtime issued: {nested!r}"
                ),
            )

        local_delivery.run_validated_local_delivery(
            bind_host="127.0.0.1",
            port="8000",
            server_runner=start_nested,
        )

    def test_runtime_cannot_be_constructed_as_a_public_configuration_value(self):
        with self.assertRaises(TypeError):
            local_delivery.LocalDeliveryRuntime(
                bind_host="127.0.0.1",
                port=8000,
                issuer=object(),
            )


class RunlocalCommandTests(SimpleTestCase):
    databases = set()

    def test_settings_allow_numeric_loopback_without_permissive_hosts(self):
        # Django's test runner appends ``testserver`` for its synthetic client.
        self.assertEqual(settings.ALLOWED_HOSTS[:2], ["127.0.0.1", "[::1]"])
        self.assertNotIn("*", settings.ALLOWED_HOSTS)
        self.assertNotIn("localhost", settings.ALLOWED_HOSTS)

        factory = RequestFactory()
        self.assertEqual(
            factory.get("/", HTTP_HOST="127.0.0.1:8000").get_host(),
            "127.0.0.1:8000",
        )
        self.assertEqual(
            factory.get("/", HTTP_HOST="[::1]:8000").get_host(),
            "[::1]:8000",
        )
        with self.assertRaises(DisallowedHost):
            factory.get("/", HTTP_HOST="localhost:8000").get_host()

    def test_unsafe_host_fails_before_server_delegation(self):
        for host in ("0.0.0.0", "::", "192.168.1.10", "localhost", ""):
            with self.subTest(host=host), patch.object(
                RunlocalCommand,
                "_serve",
            ) as serve, self.assertRaises(CommandError) as caught:
                call_command("runlocal", host=host, port="8000")

            self.assertEqual(str(caught.exception), "bind_host_invalid")
            serve.assert_not_called()

    def test_missing_host_fails_before_server_delegation(self):
        with patch.object(RunlocalCommand, "_serve") as serve, self.assertRaises(
            CommandError
        ) as caught:
            call_command("runlocal")

        self.assertIn(
            "the following arguments are required: --host",
            str(caught.exception),
        )
        serve.assert_not_called()
        with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
            local_delivery.require_active_local_delivery_runtime()

    def test_invalid_port_fails_before_server_delegation(self):
        with patch.object(RunlocalCommand, "_serve") as serve, self.assertRaises(
            CommandError
        ) as caught:
            call_command("runlocal", host="127.0.0.1", port="not-a-port")

        self.assertEqual(str(caught.exception), "port_invalid")
        serve.assert_not_called()

    def test_valid_command_delegates_while_runtime_is_active(self):
        captured = []

        def capture(runtime):
            captured.append(runtime)
            self.assertIs(
                local_delivery.require_active_local_delivery_runtime(),
                runtime,
            )
            self.assertIsNotNone(runtime.trusted_principal_context())

        with patch.object(RunlocalCommand, "_serve", side_effect=capture) as serve:
            call_command("runlocal", host="::1", port="8123")

        serve.assert_called_once_with(captured[0])
        self.assertEqual(captured[0].django_addrport, "[::1]:8123")
        with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
            local_delivery.require_active_local_delivery_runtime()

    def test_server_delegation_receives_only_bootstrap_derived_bind(self):
        command = RunlocalCommand()
        with patch.object(RunserverCommand, "handle") as runserver:
            local_delivery.run_validated_local_delivery(
                bind_host="127.0.0.1",
                port="8123",
                server_runner=command._serve,
            )

        runserver.assert_called_once_with(
            addrport="127.0.0.1:8123",
            use_ipv6=False,
            use_threading=True,
            use_reloader=False,
            skip_checks=False,
        )

    def test_server_delegation_without_active_bootstrap_fails_closed(self):
        command = RunlocalCommand()
        with self.assertRaises(TypeError):
            local_delivery.LocalDeliveryRuntime(
                bind_host="127.0.0.1",
                port=8000,
                issuer=object(),
            )

        with patch.object(RunserverCommand, "handle") as runserver, self.assertRaises(
            local_delivery.LocalDeliveryBootstrapError
        ) as caught:
            command._serve(object())

        self.assertEqual(caught.exception.code, "local_delivery_not_active")
        runserver.assert_not_called()

    def test_generic_runserver_asgi_and_wsgi_do_not_activate_runtime(self):
        def assert_generic_runner_has_no_capability(command, **options):
            with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
                local_delivery.require_active_local_delivery_runtime()

        with patch.object(
            RunserverCommand,
            "run",
            autospec=True,
            side_effect=assert_generic_runner_has_no_capability,
        ) as runserver:
            call_command(
                "runserver",
                "127.0.0.1:8000",
                use_reloader=False,
            )

        runserver.assert_called_once()
        for module_name in ("config.asgi", "config.wsgi"):
            with self.subTest(module=module_name):
                reload(import_module(module_name))
                with self.assertRaises(local_delivery.LocalDeliveryBootstrapError):
                    local_delivery.require_active_local_delivery_runtime()
