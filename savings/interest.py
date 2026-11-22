
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from accounting.models import LedgerEntry
from notifications.models import Notification

from .models import SavingsAccount, SavingsInterestPosting


ANNUAL_RATE = Decimal("2.00")
MONTHLY_DIVISOR = Decimal("1200")
CENT = Decimal("0.01")


def calculate_monthly_interest(balance, annual_rate=ANNUAL_RATE):
    balance = Decimal(str(balance))
    annual_rate = Decimal(str(annual_rate))

    return (
        balance * annual_rate / MONTHLY_DIVISOR
    ).quantize(CENT, rounding=ROUND_HALF_UP)


def post_monthly_interest(year, month, by):
    year = int(year)
    month = int(month)

    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12.")

    if not 1 <= year <= 9999:
        raise ValueError("Invalid year.")

    today = timezone.localdate()

    if (year, month) >= (today.year, today.month):
        raise ValueError(
            "Only completed past months can be posted."
        )

    if (
        not by
        or not by.pk
        or not by.is_active
        or getattr(getattr(by, "role", None), "name", None)
        != "admin"
    ):
        raise ValueError("An active admin user is required.")

    results = {
        "posted": 0,
        "skipped": 0,
        "total_interest": Decimal("0.00"),
    }

    account_ids = list(
        SavingsAccount.objects.order_by("pk")
        .values_list("pk", flat=True)
    )

    for account_id in account_ids:
        with transaction.atomic():
            account = (
                SavingsAccount.objects
                .select_for_update()
                .select_related("client__user")
                .get(pk=account_id)
            )

            if account.status != SavingsAccount.Status.ACTIVE:
                results["skipped"] += 1
                continue

            already_posted = SavingsInterestPosting.objects.filter(
                savings_account=account,
                year=year,
                month=month,
            ).exists()

            if already_posted:
                results["skipped"] += 1
                continue

            interest = calculate_monthly_interest(
                account.balance
            )

            if interest <= 0:
                results["skipped"] += 1
                continue

            account.balance += interest
            account.save(update_fields=["balance"])

            reference = (
                f"INT-{year}{month:02d}-{account.pk}"
            )

            entry = LedgerEntry.objects.create(
                entry_type=LedgerEntry.EntryType.INTEREST,
                amount=interest,
                balance_after=account.balance,
                savings_account=account,
                reference=reference,
                created_by=by,
            )

            SavingsInterestPosting.objects.create(
                savings_account=account,
                ledger_entry=entry,
                year=year,
                month=month,
                annual_rate=ANNUAL_RATE,
                amount=interest,
                posted_by=by,
            )

            Notification.objects.create(
                user=account.client.user,
                kind="savings_interest",
                message=(
                    f"Monthly savings interest of "
                    f"PHP {interest:,.2f} was credited "
                    f"for {year}-{month:02d}."
                ),
            )

            results["posted"] += 1
            results["total_interest"] += interest

    return results
