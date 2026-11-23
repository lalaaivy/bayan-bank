from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
import re

from .models import Notification


def notification_destination(notification):
    role = getattr(
        getattr(notification.user, "role", None),
        "name",
        "",
    )

    kind = str(getattr(notification, "kind", "")).lower()

    if role == "client":
        if any(
            word in kind
            for word in (
                "loan",
                "payment",
                "repayment",
                "installment",
                "agreement",
            )
        ):
            return "portal_loans"

        if any(
            word in kind
            for word in (
                "saving",
                "deposit",
                "withdraw",
                "transfer",
                "interest",
            )
        ):
            return "portal_savings"

        return "portal_home"

    if role == "admin":
        if "client" in kind or "verification" in kind:
            return "staff_clients"

        if "loan" in kind or "overdue" in kind:
            return "staff_loans"

        if (
            "transaction" in kind
            or "transfer" in kind
            or "withdraw" in kind
        ):
            return "bank_transactions"

        return "staff_home"

    if role == "loan_officer":
        if "loan" in kind or "payment" in kind:
            return "staff_loans"

        return "staff_home"

    if role == "staff":
        if "client" in kind or "verification" in kind:
            return "staff_clients"

        if "payment" in kind or "repayment" in kind:
            return "staff_payments"

        if "saving" in kind:
            return "staff_savings"

        if "bank" in kind or "transaction" in kind:
            return "bank_transactions"

        if "loan" in kind:
            return "staff_loans"

        return "staff_home"

    return "home"


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        user=request.user,
    ).order_by("-created_at", "-id")

    unread_count = notifications.filter(
        is_read=False,
    ).count()

    role = getattr(
        getattr(request.user, "role", None),
        "name",
        None,
    )

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


@login_required
@require_POST
def notification_open(request, notification_id):
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        user=request.user,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    role = getattr(getattr(request.user, "role", None), "name", None)
    if notification.kind in {"admin_client_pending", "client_id_uploaded"}:
        match = re.search(r"Client #?(\d+)|client #?(\d+)", notification.message)
        if match:
            client_id = int(next(group for group in match.groups() if group))
            if role == "staff":
                return redirect("verify_client_detail", client_id=client_id)
            if role == "admin":
                return redirect("staff_client_detail", client_id=client_id)

    if role == "loan_officer" and notification.kind == "loan_application_submitted":
        match = re.search(r"Application ID:\s*(\d+)", notification.message, re.IGNORECASE)
        if match:
            return redirect("loan_application_detail", loan_id=int(match.group(1)))

    return redirect(notification_destination(notification))


@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return redirect("notification_list")


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return redirect("notification_list")