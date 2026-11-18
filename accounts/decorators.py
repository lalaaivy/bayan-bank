from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied


def role_required(*roles):
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *a, **kw):
            if request.user.role.name not in roles:
                raise PermissionDenied
            return view(request, *a, **kw)
        return wrapper
    return deco


def client_required(view):
    """Only clients that have a Client profile. Adds request.client for the view."""
    @role_required("client")
    @wraps(view)
    def wrapper(request, *a, **kw):
        try:
            request.client = request.user.client_profile
        except ObjectDoesNotExist:
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper