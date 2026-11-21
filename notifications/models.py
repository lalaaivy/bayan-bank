
from django.conf import settings
from django.db import models


class Notification(models.Model):

    class Kind(models.TextChoices):
        LOAN_APPROVED = "loan_approved", "Loan Approved"
        LOAN_REJECTED = "loan_rejected", "Loan Rejected"
        AGREEMENT_READY = "agreement_ready", "Loan Agreement Ready"
        LOAN_DISBURSED = "loan_disbursed", "Loan Disbursed"
        LOAN_PAYMENT_RECORDED = (
            "loan_payment_recorded",
            "Loan Payment Recorded",
        )
        INSTALLMENT_OVERDUE = "installment_overdue", "Installment Overdue"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    kind = models.CharField(
        max_length=30,
        choices=Kind.choices,
    )

    message = models.CharField(max_length=255)

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notif_user_read_date_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_kind_display()}"
