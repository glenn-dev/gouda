"""Remove only Gouda's deterministic synthetic local demo dataset."""

from django.core.management import BaseCommand, CommandError

from gouda.ledger.demo_data import DemoDataError, clear_demo_data


class Command(BaseCommand):
    help = "Remove only the deterministic synthetic local demo dataset."

    def handle(self, *args, **options):
        try:
            result = clear_demo_data()
        except DemoDataError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data cleared: {result.accounts} Accounts, "
                f"{result.movements} Movements."
            )
        )
