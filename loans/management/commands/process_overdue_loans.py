
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from loans.models import Installment, Loan
from notifications.models import Notification


PENALTY_RATE = Decimal("0.02")
CENT = Decimal("0.01")


class Command(BaseCommand):
    help = "Mark overdue installments, apply one-time penalties, and notify clients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=date.fromisoformat,
            default=None,
            help="Processing date in YYYY-MM-DD format.",
        )

    def handle(self, *args, **options):
        today = options["date"] or timezone.localdate()

        overdue_count = 0
        penalty_count = 0
        paid_count = 0
        notification_count = 0

        with transaction.atomic():
            installments = (
                Installment.objects.select_for_update()
                .filter(
                    loan__status=Loan.Status.ACTIVE,
                    due_date__lt=today,
                )
                .exclude(status=Installment.Status.PAID)
                .select_related("loan__client__user")
                .order_by("pk")
            )

            for installment in installments:
                unpaid = (
                    installment.total_due
                    - installment.amount_paid
                )

                if unpaid <= 0:
                    installment.status = Installment.Status.PAID
                    installment.paid_at = timezone.now()
                    installment.save(
                        update_fields=["status", "paid_at"]
                    )
                    continue

                fields = []
                newly_overdue = False

                newly_overdue = (
                    installment.status != Installment.Status.OVERDUE
                )

                if newly_overdue:
                    installment.status = Installment.Status.OVERDUE
                    fields.append("status")
                    overdue_count += 1
                    newly_overdue = True

                    loan = installment.loan

                    Notification.objects.create(
                        user=loan.client.user,
                        kind=Notification.Kind.INSTALLMENT_OVERDUE,
                        message=(
                            f"Your installment #{installment.number} "
                            f"for loan #{loan.pk} is overdue. "
                            f"Outstanding amount: P{unpaid:,.2f}."
                        ),
                    )

                    notification_count += 1

                if installment.penalty_amount == 0:
                    penalty = (
                        unpaid * PENALTY_RATE
                    ).quantize(
                        CENT,
                        rounding=ROUND_HALF_UP,
                    )

                    if penalty > 0:
                        installment.penalty_amount = penalty
                        fields.append("penalty_amount")
                        penalty_count += 1

                if fields:
                    installment.save(update_fields=fields)

                if newly_overdue:
                    outstanding = (
                        installment.total_due
                        - installment.amount_paid
                    )

                    Notification.objects.create(
                        user=installment.loan.client.user,
                        kind="loan_overdue",
                        message=(
                            f"Loan #{installment.loan_id}, "
                            f"installment #{installment.number} "
                            f"is overdue. Outstanding amount: "
                            f"PHP {outstanding:,.2f}."
                        )[:255],
                    )

                    notification_count += 1

            active_loans = (
                Loan.objects.select_for_update()
                .filter(status=Loan.Status.ACTIVE)
                .prefetch_related("installments")
            )

            for loan in active_loans:
                loan_installments = list(
                    loan.installments.all()
                )

                if not loan_installments:
                    continue

                if all(
                    inst.amount_paid >= inst.total_due
                    for inst in loan_installments
                ):
                    loan.status = Loan.Status.PAID
                    loan.save(update_fields=["status"])
                    paid_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processing date: {today}\n"
                f"Newly overdue: {overdue_count}\n"
                f"New penalties: {penalty_count}\n"
                f"New overdue notifications: {notification_count}\n"
                f"Loans marked paid: {paid_count}"
            )
        )
