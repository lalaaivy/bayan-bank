from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from accounting.models import BankAccount
from audit.services import log
from notifications.models import Notification
from savings.models import SavingsAccount

from .models import (
    Client,
    ReactivationRequest,
    SecurityFreeze,
    SecurityFreezeBankAccount,
    SecurityFreezeSavingsAccount,
)


User = get_user_model()


def _role_name(user):
    return getattr(getattr(user, "role", None), "name", "")


def _require_admin(user):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication is required.")

    if _role_name(user) != "admin":
        raise PermissionDenied(
            "Only administrators can perform this action."
        )


def _require_staff_or_admin(user):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication is required.")

    if _role_name(user) not in ("admin", "staff"):
        raise PermissionDenied(
            "Only authorized staff or administrators can perform this action."
        )


def client_has_active_security_freeze(client):
    """
    Return True when the client has an active security freeze.

    Accepts either a Client instance or a client ID.
    """

    client_id = getattr(client, "pk", client)

    return SecurityFreeze.objects.filter(
        client_id=client_id,
        status=SecurityFreeze.Status.ACTIVE,
    ).exists()


def _notify(user, kind, message):
    """
    Create a notification for one user.
    """

    if user:
        Notification.objects.create(
            user=user,
            kind=kind,
            message=message[:255],
        )


def _notify_reactivation_reviewers(request_record):
    """
    Notify every active administrator and staff member
    that a client has submitted a reactivation request.
    """

    reviewers = User.objects.filter(
        is_active=True,
        role__name__in=("admin", "staff"),
    )

    message = (
        f"Client {request_record.client_id} has submitted a "
        f"reactivation request. Please review request "
        f"#{request_record.pk}."
    )

    notifications = [
        Notification(
            user=reviewer,
            kind=Notification.Kind.REACTIVATION_REQUESTED,
            message=message[:255],
        )
        for reviewer in reviewers
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)


@transaction.atomic
def freeze_client(client_id, severity, reason, frozen_by):
    """
    Freeze the client's regular bank and savings accounts.

    Minor freezes expire after 24 hours.
    Serious freezes require manual release after branch verification.

    Only administrators may create security freezes.
    """

    _require_admin(frozen_by)

    if severity not in SecurityFreeze.Severity.values:
        raise ValueError("Invalid security-freeze severity.")

    reason = (reason or "").strip()

    if not reason:
        raise ValueError("A reason is required for a security freeze.")

    client = (
        Client.objects
        .select_for_update()
        .select_related("user")
        .get(pk=client_id)
    )

    if SecurityFreeze.objects.filter(
        client=client,
        status=SecurityFreeze.Status.ACTIVE,
    ).exists():
        raise ValueError(
            "This client already has an active security freeze."
        )

    now = timezone.now()

    expires_at = (
        now + timedelta(hours=24)
        if severity == SecurityFreeze.Severity.MINOR
        else None
    )

    security_freeze = SecurityFreeze.objects.create(
        client=client,
        severity=severity,
        status=SecurityFreeze.Status.ACTIVE,
        reason=reason,
        expires_at=expires_at,
        frozen_by=frozen_by,
    )

    bank_accounts = (
        BankAccount.objects
        .select_for_update()
        .filter(client=client)
        .order_by("pk")
    )

    for account in bank_accounts:
        changed_status = account.status == BankAccount.Status.ACTIVE

        if changed_status:
            account.status = BankAccount.Status.FROZEN
            account.save(update_fields=["status"])

        SecurityFreezeBankAccount.objects.create(
            security_freeze=security_freeze,
            bank_account=account,
            changed_status=changed_status,
        )

    savings_accounts = (
        SavingsAccount.objects
        .select_for_update()
        .filter(client=client)
        .order_by("pk")
    )

    for account in savings_accounts:
        changed_status = account.status == SavingsAccount.Status.ACTIVE

        if changed_status:
            account.status = SavingsAccount.Status.FROZEN
            account.save(update_fields=["status"])

        SecurityFreezeSavingsAccount.objects.create(
            security_freeze=security_freeze,
            savings_account=account,
            changed_status=changed_status,
        )

    log(
        frozen_by,
        "client_security_freeze",
        client,
        severity=severity,
        reason=reason,
        freeze_id=security_freeze.pk,
        expires_at=(
            expires_at.isoformat()
            if expires_at
            else "Manual release required"
        ),
    )

    _notify(
        client.user,
        Notification.Kind.SECURITY_FREEZE,
        (
            "Your Bayan Bank account has been temporarily restricted "
            "for a security review."
            if severity == SecurityFreeze.Severity.MINOR
            else
            "Your Bayan Bank account has been restricted. "
            "Please visit a branch for identity verification and review."
        ),
    )

    return security_freeze


@transaction.atomic
def release_security_freeze(
    freeze_id,
    released_by=None,
    branch_reference="",
    staff_notes="",
    automatic=False,
):
    """
    Release an active security freeze.

    Manual release is available to staff and administrators.
    Serious freezes require a branch verification reference.

    Automatic release is allowed only for expired minor freezes.
    """

    if not automatic:
        _require_staff_or_admin(released_by)

    security_freeze = (
        SecurityFreeze.objects
        .select_for_update()
        .select_related("client", "client__user")
        .get(pk=freeze_id)
    )

    if security_freeze.status != SecurityFreeze.Status.ACTIVE:
        raise ValueError(
            "This security freeze is no longer active."
        )

    now = timezone.now()

    if automatic:
        if security_freeze.severity != SecurityFreeze.Severity.MINOR:
            raise ValueError(
                "Serious freezes cannot expire automatically."
            )

        if (
            not security_freeze.expires_at
            or security_freeze.expires_at > now
        ):
            raise ValueError(
                "This temporary freeze has not expired yet."
            )

        new_status = SecurityFreeze.Status.EXPIRED

    else:
        if security_freeze.severity == SecurityFreeze.Severity.SERIOUS:
            branch_reference = (branch_reference or "").strip()

            if not branch_reference:
                raise ValueError(
                    "A branch verification reference is required "
                    "to release a serious security freeze."
                )

        new_status = SecurityFreeze.Status.RELEASED

    bank_records = (
        security_freeze.bank_account_records
        .select_related("bank_account")
        .select_for_update()
    )

    for record in bank_records:
        account = record.bank_account

        if (
            record.changed_status
            and account.status == BankAccount.Status.FROZEN
        ):
            account.status = BankAccount.Status.ACTIVE
            account.save(update_fields=["status"])

    savings_records = (
        security_freeze.savings_account_records
        .select_related("savings_account")
        .select_for_update()
    )

    for record in savings_records:
        account = record.savings_account

        if (
            record.changed_status
            and account.status == SavingsAccount.Status.FROZEN
        ):
            account.status = SavingsAccount.Status.ACTIVE
            account.save(update_fields=["status"])

    security_freeze.status = new_status
    security_freeze.ended_at = now
    security_freeze.unfrozen_by = released_by
    security_freeze.branch_reference = branch_reference or ""
    security_freeze.staff_notes = staff_notes or ""

    security_freeze.save(
        update_fields=[
            "status",
            "ended_at",
            "unfrozen_by",
            "branch_reference",
            "staff_notes",
        ]
    )

    log(
        released_by,
        (
            "client_security_freeze_expired"
            if automatic
            else "client_security_freeze_released"
        ),
        security_freeze.client,
        freeze_id=security_freeze.pk,
        severity=security_freeze.severity,
        branch_reference=branch_reference or "",
        automatic=automatic,
    )

    _notify(
        security_freeze.client.user,
        Notification.Kind.SECURITY_UNFREEZE,
        (
            "Your temporary Bayan Bank security restriction has expired. "
            "Your account is available again, subject to other restrictions."
            if automatic
            else
            "Your Bayan Bank security restriction has been released. "
            "Your account is available again, subject to other restrictions."
        ),
    )

    return security_freeze


@transaction.atomic
def expire_temporary_security_freezes():
    """
    Expire all minor security freezes whose 24-hour period has ended.

    This function must be called by a scheduled management command.
    Serious freezes are never automatically released.
    """

    now = timezone.now()

    expired_ids = list(
        SecurityFreeze.objects.filter(
            status=SecurityFreeze.Status.ACTIVE,
            severity=SecurityFreeze.Severity.MINOR,
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    results = []

    for freeze_id in expired_ids:
        try:
            result = release_security_freeze(
                freeze_id=freeze_id,
                automatic=True,
            )
            results.append(result.pk)

        except SecurityFreeze.DoesNotExist:
            continue

        except ValueError:
            continue

    return results


@transaction.atomic
def submit_reactivation_request(client_id, reason):
    """
    Submit a public client reactivation request.

    The request is sent to active administrators and staff.
    The client's login is not reactivated here.
    """

    reason = (reason or "").strip()

    if len(reason) < 10:
        raise ValueError(
            "Please provide a reason with at least 10 characters."
        )

    client = (
        Client.objects
        .select_for_update()
        .select_related("user")
        .get(pk=client_id)
    )

    if client.user.is_active:
        raise ValueError(
            "This client account is already active."
        )

    existing_request = ReactivationRequest.objects.filter(
        client=client,
        status=ReactivationRequest.Status.PENDING,
    ).first()

    if existing_request:
        raise ValueError(
            "A reactivation request is already pending for this client."
        )

    request_record = ReactivationRequest.objects.create(
        client=client,
        reason=reason,
    )

    log(
        None,
        "client_reactivation_requested",
        client,
        request_id=request_record.pk,
    )

    # Notify the client.
    _notify(
        client.user,
        Notification.Kind.REACTIVATION_REQUESTED,
        "Your reactivation request has been received and is awaiting review.",
    )

    # Notify active administrators and staff reviewers.
    _notify_reactivation_reviewers(request_record)

    return request_record


@transaction.atomic
def review_reactivation_request(
    request_id,
    reviewed_by,
    approved,
    staff_notes="",
    branch_reference="",
):
    """
    Approve or reject a client reactivation request.

    Staff and administrators may review requests.
    Approval requires a branch verification reference.
    """

    _require_staff_or_admin(reviewed_by)

    request_record = (
        ReactivationRequest.objects
        .select_for_update()
        .select_related("client", "client__user")
        .get(pk=request_id)
    )

    if request_record.status != ReactivationRequest.Status.PENDING:
        raise ValueError(
            "This request has already been reviewed."
        )

    client = (
        Client.objects
        .select_for_update()
        .select_related("user")
        .get(pk=request_record.client_id)
    )

    if approved:
        branch_reference = (branch_reference or "").strip()

        if not branch_reference:
            raise ValueError(
                "A branch verification reference is required "
                "before reactivating a client."
            )

        if client.user.is_active:
            raise ValueError(
                "This client's login is already active."
            )

        client.user.is_active = True
        client.user.save(update_fields=["is_active"])

        request_record.status = ReactivationRequest.Status.APPROVED

    else:
        request_record.status = ReactivationRequest.Status.REJECTED

    request_record.reviewed_by = reviewed_by
    request_record.reviewed_at = timezone.now()
    request_record.staff_notes = staff_notes or ""
    request_record.branch_reference = branch_reference or ""

    request_record.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "staff_notes",
            "branch_reference",
        ]
    )

    log(
        reviewed_by,
        (
            "client_reactivation_approved"
            if approved
            else "client_reactivation_rejected"
        ),
        client,
        request_id=request_record.pk,
        branch_reference=branch_reference or "",
    )

    _notify(
        client.user,
        (
            Notification.Kind.REACTIVATION_APPROVED
            if approved
            else Notification.Kind.REACTIVATION_REJECTED
        ),
        (
            "Your Bayan Bank login has been reactivated."
            if approved
            else
            "Your reactivation request was not approved. "
            "Please contact a branch for assistance."
        ),
    )

    return request_record