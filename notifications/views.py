import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from .models import Notification


# --------------------------------------------------
# Notification destinations
# --------------------------------------------------

def _user_role(user):
    """Return the current user's banking role."""
    return getattr(
        getattr(user, "role", None),
        "name",
        "",
    ) or ""


def _extract_loan_id(message):
    """
    Extract a loan ID from existing notification messages.

    Supported examples:
        Loan #2 has been disbursed.
        New loan application #3 was submitted.
        Application ID: 4
        for loan #5
    """
    patterns = (
        r"\bapplication\s+ID\s*:\s*(\d+)\b",
        r"\bloan\s+application\s*#?\s*(\d+)\b",
        r"\bloan\s*#\s*(\d+)\b",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            message or "",
            flags=re.IGNORECASE,
        )

        if match:
            return int(match.group(1))

    return None


def _extract_client_id(message):
    """
    Extract a client ID from existing notification messages.

    Supported examples:
        Client #3 is pending verification.
        Client #5 uploaded an ID.
    """
    match = re.search(
        r"\bclient\s*#\s*(\d+)\b",
        message or "",
        flags=re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def _is_loan_notification(kind):
    return (
        "loan" in kind
        or "application" in kind
        or "agreement" in kind
        or "installment" in kind
        or "repayment" in kind
        or kind == "admin_loan_status"
    )


def _is_savings_notification(kind):
    return (
        "saving" in kind
        or "interest" in kind
        or "early_wd" in kind
    )


def _is_client_notification(kind):
    return (
        "client" in kind
        or "verification" in kind
        or "reactivation" in kind
        or "security" in kind
    )


def _is_security_notification(kind):
    return "security" in kind


def _is_reactivation_notification(kind):
    return "reactivation" in kind


def _is_payment_notification(kind):
    return (
        "payment" in kind
        or "repayment" in kind
    )


def _safe_reverse(name, **kwargs):
    """
    Return a URL only when the named route exists.

    This prevents notification navigation from crashing
    if a route changes in a future update.
    """
    try:
        return reverse(name, kwargs=kwargs or None)
    except NoReverseMatch:
        return None


def notification_destination(notification):
    """
    Determine where a notification should lead.

    Uses existing role-specific routes and extracts
    record IDs from older notification messages.

    All destination views retain their own permissions.
    """
    role = _user_role(notification.user)
    kind = str(notification.kind or "").lower()
    message = notification.message or ""

    loan_id = _extract_loan_id(message)
    client_id = _extract_client_id(message)

    # ----------------------------------------------
    # CLIENT
    # ----------------------------------------------

    if role == "client":
        if _is_security_notification(kind):
            return _safe_reverse("portal_home")

        if _is_reactivation_notification(kind):
            return (
                _safe_reverse("portal_home")
                or _safe_reverse("home")
            )

        if _is_loan_notification(kind) or _is_payment_notification(kind):
            return _safe_reverse("portal_loans") or _safe_reverse(
                "my_loans"
            )

        if (
            _is_savings_notification(kind)
            or "deposit" in kind
            or "withdraw" in kind
            or "transfer" in kind
        ):
            return _safe_reverse("portal_savings") or _safe_reverse(
                "savings_history"
            )

        return _safe_reverse("portal_home")

    # ----------------------------------------------
    # LOAN OFFICER
    # ----------------------------------------------

    if role == "loan_officer":
        if loan_id is not None:
            url = _safe_reverse(
                "loan_application_detail",
                loan_id=loan_id,
            )
            if url:
                return url

        if _is_loan_notification(kind) or _is_payment_notification(kind):
            return (
                _safe_reverse("loan_applications")
                or _safe_reverse("staff_loans")
            )

        return (
            _safe_reverse("officer_home")
            or _safe_reverse("staff_home")
        )

    # ----------------------------------------------
    # STAFF
    # ----------------------------------------------

    if role == "staff":
        if _is_reactivation_notification(kind):
            return (
                _safe_reverse("admin_reactivation_requests")
                or _safe_reverse("admin_clients")
                or _safe_reverse("staff_clients")
            )

        if _is_security_notification(kind):
            if client_id is not None:
                url = _safe_reverse(
                    "staff_client_detail",
                    client_id=client_id,
                )
                if url:
                    return url

            return (
                _safe_reverse("admin_clients")
                or _safe_reverse("staff_clients")
            )

        if client_id is not None and _is_client_notification(kind):
            url = _safe_reverse(
                "verify_client_detail",
                client_id=client_id,
            )
            if url:
                return url

        if loan_id is not None:
            url = _safe_reverse(
                "staff_loan",
                loan_id=loan_id,
            )
            if url:
                return url

        if _is_client_notification(kind):
            return _safe_reverse("verify_clients") or _safe_reverse(
                "staff_clients"
            )

        if _is_payment_notification(kind):
            return _safe_reverse("staff_payments")

        if _is_savings_notification(kind):
            return _safe_reverse("staff_savings")

        if "bank" in kind or "transaction" in kind:
            return _safe_reverse("bank_transactions")

        if _is_loan_notification(kind):
            return _safe_reverse("staff_loans")

        return _safe_reverse("staff_home")

    # ----------------------------------------------
    # ADMIN
    # ----------------------------------------------

    if role == "admin":
        if _is_reactivation_notification(kind):
            return (
                _safe_reverse("admin_reactivation_requests")
                or _safe_reverse("admin_clients")
                or _safe_reverse("staff_clients")
            )

        if client_id is not None and _is_client_notification(kind):
            url = _safe_reverse(
                "staff_client_detail",
                client_id=client_id,
            )
            if url:
                return url

        if _is_security_notification(kind):
            return (
                _safe_reverse("admin_clients")
                or _safe_reverse("staff_clients")
            )

        if loan_id is not None:
            url = _safe_reverse(
                "staff_loan",
                loan_id=loan_id,
            )
            if url:
                return url

        if _is_client_notification(kind):
            return (
                _safe_reverse("admin_clients")
                or _safe_reverse("staff_clients")
            )

        if _is_loan_notification(kind) or _is_payment_notification(kind):
            return _safe_reverse("staff_loans")

        if (
            "transaction" in kind
            or "transfer" in kind
            or "withdraw" in kind
            or "deposit" in kind
        ):
            return (
                _safe_reverse("bank_transactions")
                or _safe_reverse("admin_reports")
            )

        if _is_savings_notification(kind):
            return _safe_reverse("admin_reports")

        return (
            _safe_reverse("admin_home")
            or _safe_reverse("staff_home")
        )

    return _safe_reverse("home")


# --------------------------------------------------
# Notification list
# --------------------------------------------------

@login_required
def notification_list(request):
    notifications = (
        Notification.objects
        .filter(user=request.user)
        .order_by("-created_at", "-id")
    )

    unread_count = notifications.filter(
        is_read=False,
    ).count()

    role = _user_role(request.user)

    if role == "client":
        template_name = "notifications/list.html"
    else:
        template_name = "notifications/list_staff.html"

    return render(
        request,
        template_name,
        {
            "notifications": notifications,
            "unread_count": unread_count,
        },
    )


# --------------------------------------------------
# Open notification and mark as read
# --------------------------------------------------

@login_required
@require_POST
def notification_open(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    destination = notification_destination(notification)

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    if destination:
        return redirect(destination)

    return redirect("notification_list")


# --------------------------------------------------
# Mark one notification as read
# --------------------------------------------------

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return redirect("notification_list")


# --------------------------------------------------
# Mark all notifications as read
# --------------------------------------------------

@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return redirect("notification_list")


# --------------------------------------------------
# Compatibility with older notification routes
# --------------------------------------------------

@login_required
@require_POST
def notification_mark_all_read(request):
    return mark_all_notifications_read(request)