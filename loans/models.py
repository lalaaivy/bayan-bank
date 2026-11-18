from django.conf import settings
from django.db import models


class LoanProduct(models.Model):
    name = models.CharField(max_length=100)
    annual_rate = models.DecimalField(max_digits=5, decimal_places=2)
    min_amount = models.DecimalField(max_digits=14, decimal_places=2)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)
    min_months = models.PositiveSmallIntegerField()
    max_months = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Loan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        ACTIVE = "active"
        PAID = "paid"
        DEFAULTED = "defaulted"

    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="loans")
    product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT)
    principal = models.DecimalField(max_digits=14, decimal_places=2)
    annual_rate = models.DecimalField(max_digits=5, decimal_places=2)  # copied from product
    term_months = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    applied_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=255, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Loan #{self.pk} ({self.client})"


class Installment(models.Model):
    class Status(models.TextChoices):
        DUE = "due"
        PAID = "paid"
        OVERDUE = "overdue"

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="installments")
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    principal_due = models.DecimalField(max_digits=14, decimal_places=2)
    interest_due = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DUE)

    class Meta:
        ordering = ["loan", "number"]
        constraints = [
            models.UniqueConstraint(fields=["loan", "number"], name="unique_installment_number"),
        ]

    @property
    def total_due(self):
        return self.principal_due + self.interest_due