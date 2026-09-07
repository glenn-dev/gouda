"""Start Gouda through its validated loopback-only delivery boundary."""

from argparse import Action

from django.core.management import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    LocalDeliveryRuntime,
    require_active_local_delivery_runtime,
    run_validated_local_delivery,
)


class _Once(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        marker = "_seen_" + self.dest
        if getattr(namespace, marker, False):
            parser.error("duplicate startup option")
        setattr(namespace, marker, True)
        setattr(namespace, self.dest, True if self.nargs == 0 else values)


class Command(RunserverCommand):
    help = "Start Gouda through its validated unauthenticated local delivery boundary."

    def add_arguments(self, parser):
        parser.allow_abbrev = False
        parser.add_argument(
            "--host",
            action=_Once,
            required=True,
            help="Numeric loopback bind: 127.0.0.1 or ::1.",
        )
        parser.add_argument(
            "--port",
            action=_Once,
            default="8000",
            help="TCP port from 1 through 65535 (default: 8000).",
        )
        parser.add_argument(
            "--trusted-container-network",
            action=_Once, nargs=0, default=False,
            help=(
                "Permit only the internal 0.0.0.0:8000 bind behind repository-owned "
                "numeric-loopback browser edge and trusted Compose networks."
            ),
        )
        parser.add_argument(
            "--enable-classification-writes", action=_Once, nargs=0, default=False,
            help="Explicitly enable only local Movement classification writes.",
        )
        parser.add_argument(
            "--classification-write-origin", action=_Once,
            help="Required with write activation: http://127.0.0.1:5173.",
        )

    def handle(self, *args, **options):
        try:
            run_validated_local_delivery(
                bind_host=options["host"],
                port=options["port"],
                trusted_container_network=options["trusted_container_network"],
                enable_classification_writes=options["enable_classification_writes"],
                classification_write_origin=options["classification_write_origin"],
                server_runner=self._serve,
            )
        except LocalDeliveryBootstrapError as error:
            raise CommandError(error.code) from None

    def _serve(self, runtime: LocalDeliveryRuntime) -> None:
        """Delegate only the bootstrap-derived bind to Django's server."""

        if require_active_local_delivery_runtime() is not runtime:
            raise LocalDeliveryBootstrapError("local_delivery_not_active")

        super().handle(
            addrport=runtime.django_addrport,
            use_ipv6=runtime.uses_ipv6,
            use_threading=True,
            use_reloader=False,
            skip_checks=False,
        )
