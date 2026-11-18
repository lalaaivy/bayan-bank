from .models import AuditLog


def log(user, action, obj=None, ip=None, **details):
    """Record who did what. Call this from every service that changes data."""
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        details={key: str(value) for key, value in details.items()},
        ip_address=ip,
    )