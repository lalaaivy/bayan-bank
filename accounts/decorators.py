from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.shortcuts import redirect, render


def role_required(*roles):
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *a, **kw):
            user_role = getattr(
                getattr(request.user, "role", None),
                "name",
                "",
            )

            if user_role not in roles:
                raise PermissionDenied

            return view(request, *a, **kw)

        return wrapper

    return deco


def client_required(view):
    """
    Only clients with a Client profile may access the view.

    Adds:
        request.client
        request.active_security_freeze

    Frozen clients can still log in, but cannot access
    ordinary banking pages.
    """

    @role_required("client")
    @wraps(view)
    def wrapper(request, *a, **kw):
        try:
            request.client = request.user.client_profile
        except ObjectDoesNotExist:
            raise PermissionDenied

        # Import here to avoid circular imports.
        from clients.models import SecurityFreeze

        request.active_security_freeze = (
            SecurityFreeze.objects.filter(
                client=request.client,
                status=SecurityFreeze.Status.ACTIVE,
            )
            .order_by("-started_at")
            .first()
        )

        current_url_name = getattr(
            getattr(request, "resolver_match", None),
            "url_name",
            None,
        )

        if request.active_security_freeze:

            # Display the restricted page instead of the
            # normal dashboard.
            if current_url_name == "portal_home":
                return render(
                    request,
                    "clients/security_restricted.html",
                    {
                        "client": request.client,
                        "security_freeze": request.active_security_freeze,
                    },
                )

            # Redirect other client banking pages to the
            # restricted page through the portal_home route.
            return redirect("portal_home")

        return view(request, *a, **kw)

    return wrapper