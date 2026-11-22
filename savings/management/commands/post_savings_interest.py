
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from savings.interest import post_monthly_interest


class Command(BaseCommand):
    help = "Post monthly savings interest at 2% annual rate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            help="Interest year",
        )

        parser.add_argument(
            "--month",
            type=int,
            help="Interest month (1-12)",
        )

        parser.add_argument(
            "--by",
            type=str,
            default="admin",
            help="Username of the admin posting interest",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        previous_month = today.replace(day=1) - timedelta(days=1)

        year = options["year"]
        month = options["month"]

        if year is None and month is None:
            year = previous_month.year
            month = previous_month.month
        elif year is None or month is None:
            raise CommandError(
                "Provide both --year and --month."
            )

        User = get_user_model()

        try:
            admin = User.objects.select_related("role").get(
                username=options["by"],
                is_active=True,
                role__name="admin",
            )
        except User.DoesNotExist:
            raise CommandError(
                "Active admin account not found."
            )

        try:
            results = post_monthly_interest(
                year=year,
                month=month,
                by=admin,
            )
        except ValueError as error:
            raise CommandError(str(error))

        self.stdout.write(
            self.style.SUCCESS(
                f"Interest processing completed for "
                f"{year}-{month:02d}"
            )
        )

        self.stdout.write(
            f"Accounts credited: {results['posted']}"
        )

        self.stdout.write(
            f"Accounts skipped: {results['skipped']}"
        )

        self.stdout.write(
            f"Total interest credited: "
            f"PHP {results['total_interest']:,.2f}"
        )
