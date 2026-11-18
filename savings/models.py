from django.db import models


class SavingsAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        FROZEN = "frozen"
        CLOSED = "closed"

    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="savings_accounts")
    account_number = models.CharField(max_length=20, unique=True)
    # Cached total. Must equal the sum of its ledger entries. Only services change it.
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="savings_balance_not_negative"),
        ]

    def __str__(self):
        return self.account_number