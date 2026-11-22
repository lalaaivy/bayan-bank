
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification

from .models import Installment, Loan


@transaction.atomic
def process_overdue_installments():
    """
    Find overdue installments, update their status, and notify
    each borrower once when an installment first becomes overdue.

    Returns the number of newly overdue installments processed.
    """
    today = timezone.localdate()

    overdue_installments = (
        Installment.objects.select_for_update()
        .filter(
            loan__status=Loan.Status.ACTIVE,
            due_date__lt=today,
        )
        .exclude(status=Installment.Status.PAID)
        .select_related("loan__client__user")
        .order_by("due_date", "pk")
    )

    processed_count = 0

    for installment in overdue_installments:
        if installment.status == Installment.Status.OVERDUE:
            continue

        installment.status = Installment.Status.OVERDUE
        installment.save(update_fields=["status"])

        loan = installment.loan
        borrower = loan.client.user

        outstanding = max(
            installment.total_due - installment.amount_paid,
            0,
        )

        Notification.objects.create(
            user=borrower,
            kind=Notification.Kind.INSTALLMENT_OVERDUE,
            message=(
                f"Your loan installment #{installment.number} "
                f"for loan #{loan.pk} is overdue. "
                f"Outstanding amount: P{outstanding:,.2f}. "
                "Please contact the bank or arrange payment."
            )[:255],
        )

        processed_count += 1

    return processed_count
