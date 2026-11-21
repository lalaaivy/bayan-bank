
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


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
def mark_all_notifications_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return redirect("notification_list")
