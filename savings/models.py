from django.conf import settings
from django.db import models
from django.db.models import Q


class SavingsAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    client = models.OneToOneField(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="savings_account",
    )

    account_number = models.CharField(max_length=20, unique=True)

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
                condition=Q(balance__gte=0),
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

    class Source(models.TextChoices):
        ONLINE_TRANSFER = "online_transfer", "Online Transfer"
        BRANCH_CASH = "branch_cash", "Physical Branch Deposit"

    class Status(models.TextChoices):
        LOCKED = "locked", "Locked"
        MATURED = "matured", "Matured"
        RELEASED = "released", "Fully Released"

    savings_account = models.ForeignKey(
        SavingsAccount,
        on_delete=models.PROTECT,
        related_name="deposits",
    )

    amount = models.DecimalField(max_digits=14, decimal_places=2)

    remaining_principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    annual_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.00,
    )

    term_months = models.PositiveSmallIntegerField(
        choices=Term.choices,
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ONLINE_TRANSFER,
    )

    deposited_at = models.DateTimeField(auto_now_add=True)
    maturity_date = models.DateField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOCKED,
    )

    deposit_ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="savings_deposit",
    )

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

    released_at = models.DateTimeField(null=True, blank=True)

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
                condition=Q(amount__gt=0),
                name="savings_deposit_positive",
            ),
            models.CheckConstraint(
                condition=Q(interest_amount__gte=0),
                name="savings_deposit_interest_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(term_months__in=[3, 6, 12]),
                name="savings_deposit_valid_term",
            ),
            models.CheckConstraint(
                condition=(
                    Q(remaining_principal__isnull=True)
                    | (
                        Q(remaining_principal__gte=0)
                        & Q(remaining_principal__lte=models.F("amount"))
                    )
                ),
                name="savings_remaining_principal_valid",
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

    staff_notes = models.TextField(blank=True)
    branch_reference = models.CharField(max_length=100, blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return (
            f"Early withdrawal request - "
            f"{self.deposit.savings_account.account_number} "
            f"({self.get_status_display()})"
        )


class SavingsCashWithdrawalRequest(models.Model):
    """
    Client request to withdraw a specific amount from the entire
    SavingsAccount balance as physical cash.

    New requests use savings_account directly.
    The optional deposit field is retained for historical requests.

    Approval does not deduct funds. The balance changes only after
    staff confirms the actual physical payout.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved - Awaiting Payout"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Successfully Paid"

    savings_account = models.ForeignKey(
        SavingsAccount,
        on_delete=models.PROTECT,
        related_name="cash_withdrawal_requests",
        null=True,
        blank=True,
    )

    # Retained for compatibility with old deposit-based requests.
    deposit = models.ForeignKey(
        SavingsDeposit,
        on_delete=models.PROTECT,
        related_name="cash_withdrawal_requests",
        null=True,
        blank=True,
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="savings_cash_withdrawal_requests",
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_savings_cash_withdrawals",
        null=True,
        blank=True,
    )

    staff_notes = models.TextField(blank=True)
    branch_reference = models.CharField(max_length=100, blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_savings_cash_withdrawals",
        null=True,
        blank=True,
    )

    paid_at = models.DateTimeField(null=True, blank=True)

    payout_ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="savings_cash_withdrawal",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["savings_account"],
                condition=Q(
                    savings_account__isnull=False,
                    status="pending",
                ),
                name="one_pending_cash_withdrawal_per_account",
            ),
            models.UniqueConstraint(
                fields=["deposit"],
                condition=Q(
                    deposit__isnull=False,
                    status="pending",
                ),
                name="one_pending_savings_cash_withdrawal",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="savings_cash_withdrawal_amount_positive",
            ),
        ]

    def __str__(self):
        account_number = (
            self.savings_account.account_number
            if self.savings_account_id
            else (
                self.deposit.savings_account.account_number
                if self.deposit_id
                else "Unknown Account"
            )
        )

        return (
            f"Cash withdrawal request - {account_number} "
            f"({self.amount}, {self.get_status_display()})"
        )


class SavingsTransferRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    deposit = models.ForeignKey(
        SavingsDeposit,
        on_delete=models.PROTECT,
        related_name="transfer_requests",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="savings_transfer_requests",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_savings_transfer_requests",
        null=True,
        blank=True,
    )

    staff_notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["deposit"],
                condition=Q(status="pending"),
                name="one_pending_savings_transfer_per_deposit",
            ),
        ]

    def __str__(self):
        return (
            f"Savings transfer request - "
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
                condition=Q(month__gte=1) & Q(month__lte=12),
                name="savings_interest_valid_month",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="savings_interest_positive",
            ),
        ]

    def __str__(self):
        return (
            f"Interest: {self.savings_account.account_number} "
            f"{self.year}-{self.month:02d}"
        )