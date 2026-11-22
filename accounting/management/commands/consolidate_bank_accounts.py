
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounting.models import BankAccount
from accounting.services import transfer_between_banks
from accounting.money import BankError


class Command(BaseCommand):
    help = (
        "Move the balance from a duplicate regular bank "
        "account into the primary account, then close it."
    )

    def add_arguments(self, parser):
        parser.add_argument("--primary", required=True)
        parser.add_argument("--duplicate", required=True)
        parser.add_argument("--by", default="admin")
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Perform the consolidation",
        )

    def handle(self, *args, **options):
        primary_number = options["primary"]
        duplicate_number = options["duplicate"]

        if primary_number == duplicate_number:
            raise CommandError(
                "Primary and duplicate must be different."
            )

        User = get_user_model()

        try:
            operator = User.objects.select_related(
                "role"
            ).get(username=options["by"])
        except User.DoesNotExist:
            raise CommandError("Operator account not found.")

        if getattr(
            getattr(operator, "role", None),
            "name",
            None,
        ) not in ("admin", "staff"):
            raise CommandError(
                "Operator must have admin or staff role."
            )

        try:
            with transaction.atomic():
                accounts = list(
                    BankAccount.objects.select_for_update()
                    .filter(
                        account_number__in=[
                            primary_number,
                            duplicate_number,
                        ]
                    )
                    .order_by("pk")
                )

                if len(accounts) != 2:
                    raise CommandError(
                        "Both bank accounts must exist."
                    )

                account_map = {
                    account.account_number: account
                    for account in accounts
                }

                primary = account_map[primary_number]
                duplicate = account_map[duplicate_number]

                if primary.client_id != duplicate.client_id:
                    raise CommandError(
                        "Accounts belong to different clients."
                    )

                if primary.status != BankAccount.Status.ACTIVE:
                    raise CommandError(
                        "Primary account must be active."
                    )

                if duplicate.status != BankAccount.Status.ACTIVE:
                    raise CommandError(
                        "Duplicate account must be active."
                    )

                amount = duplicate.balance

                self.stdout.write(
                    f"Primary: {primary.account_number}"
                    f" | PHP {primary.balance:,.2f}"
                )
                self.stdout.write(
                    f"Duplicate: {duplicate.account_number}"
                    f" | PHP {duplicate.balance:,.2f}"
                )
                self.stdout.write(
                    f"Amount to move: PHP {amount:,.2f}"
                )

                if not options["execute"]:
                    self.stdout.write(
                        self.style.WARNING(
                            "Preview only. No balances changed."
                        )
                    )
                    return

                if amount > 0:
                    transfer_between_banks(
                        duplicate.pk,
                        primary.pk,
                        amount,
                        operator,
                    )

                duplicate.refresh_from_db()

                if duplicate.balance != 0:
                    raise CommandError(
                        "Duplicate account still has a balance."
                    )

                duplicate.status = BankAccount.Status.CLOSED
                duplicate.save(update_fields=["status"])

                primary.refresh_from_db()

                self.stdout.write(
                    self.style.SUCCESS(
                        "Consolidation completed."
                    )
                )
                self.stdout.write(
                    f"Active account: "
                    f"{primary.account_number}"
                )
                self.stdout.write(
                    f"Final balance: "
                    f"PHP {primary.balance:,.2f}"
                )
                self.stdout.write(
                    f"Closed account: "
                    f"{duplicate.account_number}"
                )

        except BankError as error:
            raise CommandError(str(error))
