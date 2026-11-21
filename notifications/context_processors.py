
from .models import Notification


def unread_notification_count(request):
    """
    Makes the unread notification count available
    to all templates.
    """

    if not request.user.is_authenticated:
        return {
            "unread_count": 0,
        }

    unread_count = Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).count()

    return {
        "unread_count": unread_count,
    }
