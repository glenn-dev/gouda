"""Create Gouda's deterministic synthetic local demo dataset."""

from django.core.management import BaseCommand, CommandError

from gouda.ledger.demo_data import DemoDataError, seed_demo_data


class Command(BaseCommand):
    help = "Create the deterministic synthetic-only local demo dataset."

    def handle(self, *args, **options):
        try:
            result = seed_demo_data()
        except DemoDataError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {result.accounts} Accounts, "
                f"{result.movements} Movements."
            )
        )
