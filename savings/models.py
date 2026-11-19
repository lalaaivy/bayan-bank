
from django.conf import settings
from django.db import models


class SavingsAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        FROZEN = "frozen"
        CLOSED = "closed"

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="savings_accounts",
    )

    account_number = models.CharField(
        max_length=20,
        unique=True,
    )

    # Cached balance, updated only through services.
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance__gte=0),
                name="savings_balance_not_negative",
            ),
        ]

    def __str__(self):
        return self.account_number


class SavingsInterestPosting(models.Model):
    savings_account = models.ForeignKey(
        SavingsAccount,
        on_delete=models.PROTECT,
        related_name="interest_postings",
    )

    ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="savings_interest_posting",
    )

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()

    annual_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2,
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="posted_savings_interest",
    )

    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["savings_account", "year", "month"],
                name="unique_monthly_savings_interest",
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1)
                & models.Q(month__lte=12),
                name="savings_interest_valid_month",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="savings_interest_positive",
            ),
        ]

    def __str__(self):
        return (
            f"Interest: {self.savings_account.account_number} "
            f"{self.year}-{self.month:02d}"
        )
