
from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Check overdue installments, apply penalties, "
        "and notify borrowers using the central "
        "overdue processing command."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=date.fromisoformat,
            default=None,
            help="Processing date in YYYY-MM-DD format.",
        )

    def handle(self, *args, **options):
        command_options = {
            "stdout": self.stdout,
            "stderr": self.stderr,
        }

        if options["date"] is not None:
            command_options["date"] = options["date"]

        call_command(
            "process_overdue_loans",
            **command_options,
        )
