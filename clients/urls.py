from django.urls import path

from . import views


urlpatterns = [
    # Staff client pages
    # The primary staff pages are registered in accounts/urls.py.
    # Use unique names here to avoid URL reversing conflicts.
    path(
        "staff/",
        views.staff_clients,
        name="clients_staff_list",
    ),
    path(
        "staff/<int:client_id>/",
        views.staff_client_detail,
        name="clients_staff_detail",
    ),

    # Client self-deactivation
    path(
        "deactivate/",
        views.client_deactivate,
        name="client_deactivate",
    ),

    # Public reactivation request
    path(
        "reactivation-request/",
        views.public_reactivation_request,
        name="public_reactivation_request",
    ),

    # Admin client management
    path(
        "admin/<int:client_id>/deactivate/",
        views.admin_deactivate_client,
        name="admin_deactivate_client",
    ),
    path(
        "admin/<int:client_id>/delete/",
        views.admin_delete_client,
        name="admin_delete_client",
    ),

    # Reactivation review
    path(
        "staff/reactivation-requests/",
        views.admin_reactivation_requests,
        name="admin_reactivation_requests",
    ),
    path(
        "staff/reactivation-requests/<int:request_id>/review/",
        views.admin_review_reactivation_request,
        name="admin_review_reactivation_request",
    ),

    # Security freeze controls
    path(
        "admin/<int:client_id>/freeze/",
        views.admin_freeze_client,
        name="admin_freeze_client",
    ),
    path(
        "admin/security-freezes/<int:freeze_id>/release/",
        views.admin_release_security_freeze,
        name="admin_release_security_freeze",
    ),
]