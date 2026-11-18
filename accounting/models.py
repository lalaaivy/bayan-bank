from django.conf import settings
from django.db import models


class LedgerEntry(models.Model):
    """Append-only. Corrections are new reversing entries, never edits."""

    class EntryType(models.TextChoices):
        DEPOSIT = "deposit"
        WITHDRAWAL = "withdrawal"
        TRANSFER_IN = "transfer_in"
        TRANSFER_OUT = "transfer_out"
        LOAN_DISBURSEMENT = "loan_disbursement"
        LOAN_PAYMENT = "loan_payment"

    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # always positive
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    savings_account = models.ForeignKey(
        "savings.SavingsAccount", null=True, blank=True,
        on_delete=models.PROTECT, related_name="ledger_entries",
    )
    loan = models.ForeignKey(
        "loans.Loan", null=True, blank=True,
        on_delete=models.PROTECT, related_name="ledger_entries",
    )
    reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ledger_amount_positive"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Ledger entries cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Ledger entries cannot be deleted.")