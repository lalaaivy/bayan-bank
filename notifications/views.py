
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


def notification_destination(notification):
    """
    Choose an existing page based on the notification type.
    """
    role = getattr(
        getattr(notification.user, "role", None),
        "name",
        "",
    )

    kind = notification.kind.lower()

    if role == "client":
        if any(word in kind for word in ("loan", "payment", "repayment", "installment", "agreement")):
            return "portal_loans"

        if any(word in kind for word in ("saving", "deposit", "withdraw", "transfer", "interest")):
            return "portal_savings"

        return "portal_home"

    if role in ("staff", "loan_officer", "admin"):
        if any(word in kind for word in ("loan", "payment", "repayment", "installment", "agreement")):
            return "staff_loans"

        return "staff_home"

    return "home"


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        user=request.user
    )

    return render(
        request,
        "notifications/list.html",
        {
            "notifications": notifications,
            "unread_count": notifications.filter(is_read=False).count(),
        },
    )


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

    return redirect(notification_destination(notification))


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return redirect("notification_list")
