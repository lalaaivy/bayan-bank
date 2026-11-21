
from django.conf import settings
from django.db import models


class Notification(models.Model):

    class Kind:
        LOAN_APPROVED = "loan_approved"
        LOAN_REJECTED = "loan_rejected"
        AGREEMENT_READY = "agreement_ready"
        LOAN_DISBURSED = "loan_disbursed"
        INSTALLMENT_OVERDUE = "installment_overdue"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=30)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.user} - {self.kind}"
