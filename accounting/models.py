
from django.conf import settings
from django.db import models
from django.db.models import Q, F


class BankAccount(models.Model):
    """The client's regular bank account for holding available funds."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FROZEN = "frozen", "Frozen"
        CLOSED = "closed", "Closed"

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="bank_accounts",
    )

    account_number = models.CharField(
        max_length=20,
        unique=True,
    )

    # Cached balance, updated only through financial services.
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
                name="bank_account_balance_not_negative",
            ),
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(status__in=["active", "frozen"]),
                name="one_open_bank_account_per_client",
            ),
        ]

    def __str__(self):
        return self.account_number


class LedgerEntry(models.Model):
    """Append-only. Corrections use new reversing entries."""

    class EntryType(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        TRANSFER_IN = "transfer_in", "Transfer In"
        TRANSFER_OUT = "transfer_out", "Transfer Out"
        LOAN_DISBURSEMENT = "loan_disbursement", "Loan Disbursement"
        LOAN_PAYMENT = "loan_payment", "Loan Payment"
        INTEREST_CREDIT = "interest_credit", "Interest Credit"

    entry_type = models.CharField(
        max_length=20,
        choices=EntryType.choices,
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    bank_account = models.ForeignKey(
        BankAccount,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    savings_account = models.ForeignKey(
        "savings.SavingsAccount",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    loan = models.ForeignKey(
        "loans.Loan",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="ledger_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(balance_after__isnull=True)
                    | Q(balance_after__gte=0)
                ),
                name="ledger_balance_after_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(
                    entry_type__in=[
                        "deposit",
                        "withdrawal",
                        "transfer_in",
                        "transfer_out",
                        "loan_disbursement",
                        "loan_payment",
                        "interest_credit",
                    ]
                ),
                name="ledger_valid_entry_type",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError(
                "Ledger entries cannot be edited."
            )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(
            "Ledger entries cannot be deleted."
        )


class ReportExport(models.Model):

    class ReportType(models.TextChoices):
        TRANSACTION = "transaction", "Transaction Statement"
        LOAN = "loan", "Loan Statement"

    class Format(models.TextChoices):
        PDF = "pdf", "PDF"
        XLSX = "xlsx", "Excel"

    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.TRANSACTION,
    )

    file_format = models.CharField(
        max_length=10,
        choices=Format.choices,
        default=Format.PDF,
    )

    # Regular bank account transaction statement.
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="report_exports",
    )

    # Savings account transaction statement.
    savings_account = models.ForeignKey(
        "savings.SavingsAccount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="report_exports",
    )

    loan = models.ForeignKey(
        "loans.Loan",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="report_exports",
    )

    date_from = models.DateField()
    date_to = models.DateField()

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_reports",
    )

    generated_at = models.DateTimeField(auto_now_add=True)

    filename = models.CharField(max_length=255)

    class Meta:
        ordering = ["-generated_at", "-id"]

        constraints = [
            models.CheckConstraint(
                condition=Q(date_to__gte=F("date_from")),
                name="report_valid_date_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        report_type="transaction",
                        bank_account__isnull=False,
                        savings_account__isnull=True,
                        loan__isnull=True,
                    )
                    | Q(
                        report_type="transaction",
                        bank_account__isnull=True,
                        savings_account__isnull=False,
                        loan__isnull=True,
                    )
                    | Q(
                        report_type="loan",
                        bank_account__isnull=True,
                        savings_account__isnull=True,
                        loan__isnull=False,
                    )
                ),
                name="report_valid_subject",
            ),
            models.CheckConstraint(
                condition=Q(file_format__in=["pdf", "xlsx"]),
                name="report_valid_file_format",
            ),
        ]

    def __str__(self):
        return f"{self.filename} ({self.file_format})"
