
from django.conf import settings
from django.db import models


class SavingsAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    # Each client can have exactly one savings account.
    client = models.OneToOneField(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="savings_account",
    )

    account_number = models.CharField(
        max_length=20,
        unique=True,
    )

    # Cached balance of all funds held in savings.
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


class SavingsDeposit(models.Model):
    class Term(models.IntegerChoices):
        THREE_MONTHS = 3, "3 Months"
        SIX_MONTHS = 6, "6 Months"
        TWELVE_MONTHS = 12, "12 Months"

    class Status(models.TextChoices):
        LOCKED = "locked", "Locked"
        MATURED = "matured", "Matured"
        RELEASED = "released", "Released"

    savings_account = models.ForeignKey(
        SavingsAccount,
        on_delete=models.PROTECT,
        related_name="deposits",
    )

    # Amount transferred into this individual savings deposit.
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    annual_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.00,
    )

    term_months = models.PositiveSmallIntegerField(
        choices=Term.choices,
    )

    deposited_at = models.DateTimeField(auto_now_add=True)

    maturity_date = models.DateField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOCKED,
    )

    # Original savings transfer ledger entry.
    deposit_ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="savings_deposit",
    )

    # Ledger entry created when funds are released to regular banking.
    release_ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="released_savings_deposit",
        null=True,
        blank=True,
    )

    interest_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    released_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="released_savings_deposits",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-deposited_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="savings_deposit_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(interest_amount__gte=0),
                name="savings_deposit_interest_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(term_months__in=[3, 6, 12]),
                name="savings_deposit_valid_term",
            ),
        ]

    def __str__(self):
        return (
            f"{self.savings_account.account_number} - "
            f"{self.amount} ({self.term_months} months)"
        )


class SavingsEarlyWithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    deposit = models.ForeignKey(
        SavingsDeposit,
        on_delete=models.PROTECT,
        related_name="early_withdrawal_requests",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="savings_withdrawal_requests",
    )

    reason = models.TextField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_savings_withdrawals",
        null=True,
        blank=True,
    )

    staff_notes = models.TextField(
        blank=True,
    )

    branch_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    requested_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return (
            f"Early withdrawal request - "
            f"{self.deposit.savings_account.account_number} "
            f"({self.get_status_display()})"
        )


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
