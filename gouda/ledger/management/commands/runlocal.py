"""Start Gouda through its validated loopback-only delivery boundary."""

from django.core.management import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    LocalDeliveryRuntime,
    require_active_local_delivery_runtime,
    run_validated_local_delivery,
)


class Command(RunserverCommand):
    help = "Start Gouda's unauthenticated local delivery server on numeric loopback."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            required=True,
            help="Numeric loopback bind: 127.0.0.1 or ::1.",
        )
        parser.add_argument(
            "--port",
            default="8000",
            help="TCP port from 1 through 65535 (default: 8000).",
        )

    def handle(self, *args, **options):
        try:
            run_validated_local_delivery(
                bind_host=options["host"],
                port=options["port"],
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
