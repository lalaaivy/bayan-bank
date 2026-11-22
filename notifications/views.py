from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


def notification_destination(notification):
    role = getattr(getattr(notification.user, "role", None), "name", "")
    kind = notification.kind.lower()

    if role == "client":
        if any(word in kind for word in ("loan", "payment", "repayment", "installment", "agreement")):
            return "portal_loans"
        if any(word in kind for word in ("saving", "deposit", "withdraw", "transfer", "interest")):
            return "portal_savings"
        return "portal_home"

    if role == "admin":
        if "client" in kind or "verification" in kind:
            return "staff_clients"
        if "loan" in kind or "overdue" in kind:
            return "staff_loans"
        if "transaction" in kind or "transfer" in kind or "withdraw" in kind:
            return "bank_transactions"
        return "staff_home"

    if role == "loan_officer":
        return "staff_loans" if "loan" in kind or "payment" in kind else "staff_home"

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
    notifications = Notification.objects.filter(user=request.user)
    return render(request, "notifications/list.html", {
        "notifications": notifications,
        "unread_count": notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def notification_open(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(notification_destination(notification))


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notification_list")
