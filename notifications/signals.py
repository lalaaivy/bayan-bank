"""Create admin alerts for important banking events."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounting.models import LedgerEntry
from clients.models import Client, ClientDocument
from loans.models import Loan
from .models import Notification


# Change this threshold if your bank defines a different alert amount.
LARGE_TRANSACTION_THRESHOLD = Decimal("10000.00")


def notify_roles(roles, kind, message):
    """Notify active users in the specified roles after commit."""
    def create_notifications():
        User = get_user_model()
        recipient_ids = User.objects.filter(
            is_active=True,
            role__name__in=roles,
        ).values_list("pk", flat=True)
        Notification.objects.bulk_create([
            Notification(user_id=pk, kind=kind, message=message[:255])
            for pk in recipient_ids
        ])

    transaction.on_commit(create_notifications)


def notify_admins(kind, message):
    """Preserve existing Admin-only alerts for other banking events."""
    notify_roles(("admin",), kind, message)


@receiver(pre_save, sender=Client)
def remember_client_status(sender, instance, **kwargs):
    instance._previous_verification_status = None
    if instance.pk:
        instance._previous_verification_status = sender.objects.filter(
            pk=instance.pk
        ).values_list("verification_status", flat=True).first()


@receiver(post_save, sender=Client)
def client_status_alert(sender, instance, created, **kwargs):
    if created and instance.verification_status == Client.VerificationStatus.PENDING:
        notify_roles(
            ("staff", "admin"),
            "admin_client_pending",
            f"New client #{instance.pk} ({instance.client_code}) registered and is pending verification.",
        )
    elif not created and instance._previous_verification_status != instance.verification_status:
        notify_admins(
            "admin_client_status",
            f"Client #{instance.pk} verification status changed to {instance.get_verification_status_display()}.",
        )


@receiver(post_save, sender=ClientDocument)
def client_id_upload_alert(sender, instance, created, **kwargs):
    """Alert verification staff when a client submits a new ID document."""
    if created and instance.client.verification_status == Client.VerificationStatus.PENDING:
        notify_roles(
            ("staff", "admin"),
            "client_id_uploaded",
            f"Client #{instance.client_id} ({instance.client.client_code}) uploaded an ID for verification.",
        )


@receiver(pre_save, sender=Loan)
def remember_loan_status(sender, instance, **kwargs):
    instance._previous_loan_status = None
    if instance.pk:
        instance._previous_loan_status = sender.objects.filter(
            pk=instance.pk
        ).values_list("status", flat=True).first()


@receiver(post_save, sender=Loan)
def loan_status_alert(sender, instance, created, **kwargs):
    if created:
        notify_admins(
            "admin_loan_application",
            f"New loan application #{instance.pk} was submitted for review.",
        )
    elif instance._previous_loan_status != instance.status:
        notify_admins(
            "admin_loan_status",
            f"Loan #{instance.pk} status changed to {instance.get_status_display()}.",
        )


@receiver(post_save, sender=LedgerEntry)
def large_transaction_alert(sender, instance, created, **kwargs):
    if not created or instance.amount < LARGE_TRANSACTION_THRESHOLD:
        return
    if instance.entry_type not in {
        LedgerEntry.EntryType.WITHDRAWAL,
        LedgerEntry.EntryType.TRANSFER_OUT,
        LedgerEntry.EntryType.LOAN_DISBURSEMENT,
    }:
        return
    notify_admins(
        "admin_large_transaction",
        f"High-value {instance.get_entry_type_display().lower()} of PHP {instance.amount:,.2f} recorded (entry #{instance.pk}).",
    )
