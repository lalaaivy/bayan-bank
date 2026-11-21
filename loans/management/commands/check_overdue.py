
from django.core.management.base import BaseCommand

from loans.overdue import process_overdue_installments


class Command(BaseCommand):
    help = "Check overdue loan installments and notify borrowers."

    def handle(self, *args, **options):
        processed_count = process_overdue_installments()

        if processed_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {processed_count} newly overdue installment(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "No newly overdue installments found."
                )
            )
