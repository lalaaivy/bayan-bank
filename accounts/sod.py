
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def action_roles(*allowed_roles):
    """
    Restrict an action to the specified user roles.

    The user must:
    - Be authenticated
    - Have an active account
    - Have an allowed role

    Existing view-level permissions remain in effect.
    """

    allowed = {
        str(role).strip().lower()
        for role in allowed_roles
    }

    def decorator(view_func):

        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):

            if not request.user.is_active:
                raise PermissionDenied(
                    "Your account is inactive."
                )

            role = getattr(
                getattr(request.user, "role", None),
                "name",
                None,
            )

            role = str(role or "").strip().lower()

            if role not in allowed:
                raise PermissionDenied(
                    "You are not authorized to "
                    "perform this operation."
                )

            return view_func(
                request,
                *args,
                **kwargs,
            )

        return wrapped

    return decorator
