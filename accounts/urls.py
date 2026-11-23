from functools import wraps

from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied
from django.urls import path

from loans import payments_views
from loans import views as loan_views
from savings import views as savings_views

from . import views
from .role_dashboard import role_dashboard


# --------------------------------------------------
# Separation of Duties: URL-level protection
# --------------------------------------------------

def restrict_post_to(*allowed_roles):
    """
    Allow the existing view to handle GET requests.

    For POST requests, only the specified roles may
    submit changes.

    The view's original authentication and role checks
    remain active.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                role = getattr(
                    getattr(request.user, "role", None),
                    "name",
                    None,
                )

                if role not in allowed_roles:
                    raise PermissionDenied(
                        "Your role cannot perform this action."
                    )

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def staff_only(view_func):
    """
    Restrict both viewing and processing of
    operational staff-only pages.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        role = getattr(
            getattr(request.user, "role", None),
            "name",
            None,
        )

        if role != "staff":
            raise PermissionDenied(
                "This operation is restricted to staff."
            )

        return view_func(request, *args, **kwargs)

    return wrapped


# --------------------------------------------------
# Main Pages
# --------------------------------------------------

urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    # --------------------------------------------------
    # Dashboards
    # --------------------------------------------------

    path(
        "portal/",
        views.portal_home,
        name="portal_home",
    ),

    path(
        "staff/",
        role_dashboard,
        name="staff_home",
    ),

    path(
        "officer/",
        views.officer_home,
        name="officer_home",
    ),

    path(
        "admin-panel/",
        views.admin_home,
        name="admin_home",
    ),

    # --------------------------------------------------
    # Client Portal
    # --------------------------------------------------

    path(
        "portal/loans/",
        loan_views.portal_loans,
        name="my_loans",
    ),

    path(
        "portal/savings/",
        savings_views.portal_savings,
        name="savings_history",
    ),

    path(
        "portal/notifications/",
        views.notifications,
        name="notifications",
    ),

    path(
        "portal/apply/",
        views.apply_loan,
        name="apply_loan",
    ),

    path(
        "portal/loans/detail/",
        views.loan_detail,
        name="loan_detail",
    ),

    path(
        "portal/upload-id/",
        views.upload_id,
        name="upload_id",
    ),

    path(
        "portal/accept-agreement/",
        views.accept_agreement,
        name="accept_agreement",
    ),

    path(
        "portal/profile/",
        views.client_profile,
        name="client_profile",
    ),

    path(
        "portal/profile/edit/",
        views.edit_client_profile,
        name="edit_client_profile",
    ),

    path(
        "portal/change-password/",
        views.change_password,
        name="change_password",
    ),

    # --------------------------------------------------
    # Registration
    # --------------------------------------------------

    path(
        "register/",
        views.register,
        name="register",
    ),

    path(
        "register/complete-profile/",
        views.complete_profile,
        name="complete_profile",
    ),

    # --------------------------------------------------
    # Client Management
    #
    # Admin and Staff may view clients.
    # Admin may manage client records.
    # Credit score changes are restricted to Admin.
    # --------------------------------------------------

    path(
        "staff/clients/",
        views.staff_clients,
        name="staff_clients",
    ),

    path(
        "staff/clients/<int:client_id>/",
        restrict_post_to("admin")(
            views.staff_client_detail
        ),
        name="staff_client_detail",
    ),

    path(
        "staff/clients/add/",
        views.staff_add_client,
        name="staff_add_client",
    ),

    # --------------------------------------------------
    # Client Verification
    #
    # Only Staff may approve/reject verification.
    # --------------------------------------------------

    path(
        "staff/clients/verify/",
        staff_only(
            views.verify_clients
        ),
        name="verify_clients",
    ),

    path(
        "staff/clients/verify/<int:client_id>/",
        staff_only(
            views.verify_client_detail
        ),
        name="verify_client_detail",
    ),

    path(
        "staff/clients/verify/<int:client_id>/",
        staff_only(
            views.verify_client_detail
        ),
        name="staff_verify_client",
    ),

    path(
        "staff/clients/document/<int:doc_id>/<str:side>/",
        views.client_document_file,
        name="client_document_file",
    ),

    # --------------------------------------------------
    # Payments and Savings
    #
    # Staff may process operations.
    # Admin may only view supported pages.
    # --------------------------------------------------

    path(
        "staff/payments/",
        restrict_post_to("staff")(
            payments_views.staff_payments
        ),
        name="staff_payments",
    ),

    path(
        "staff/payments/record/",
        payments_views.staff_record_payment,
        name="staff_record_payment",
    ),

    path(
        "staff/payments/history/",
        views.staff_payment_history,
        name="staff_payment_history",
    ),

    path(
        "staff/payments/receipt/",
        views.staff_receipt,
        name="staff_receipt",
    ),

    path(
        "staff/savings/",
        restrict_post_to("staff")(
            views.staff_savings
        ),
        name="staff_savings",
    ),

    # --------------------------------------------------
    # Loan Release
    #
    # Only Staff may release approved loans.
    # --------------------------------------------------

    path(
        "staff/loans/release/",
        staff_only(
            views.release_loans
        ),
        name="release_loans",
    ),

    path(
        "staff/loans/release/confirm/",
        staff_only(
            views.confirm_loan_release
        ),
        name="confirm_loan_release",
    ),

    # --------------------------------------------------
    # Loan Officer
    #
    # Admin may view loan applications.
    # Only Loan Officers may approve/reject.
    # --------------------------------------------------

    path(
        "officer/applications/",
        views.loan_applications,
        name="loan_applications",
    ),

    path(
        "officer/applications/<int:loan_id>/",
        restrict_post_to("loan_officer")(
            views.loan_application_detail
        ),
        name="loan_application_detail",
    ),

    path(
        "officer/loans/",
        views.officer_loans,
        name="officer_loans",
    ),

    path(
        "officer/loans/detail/",
        views.officer_loan_detail,
        name="officer_loan_detail",
    ),

    # --------------------------------------------------
    # Admin Panel
    # --------------------------------------------------

    path(
        "admin-panel/users/",
        views.admin_users,
        name="admin_users",
    ),

    path(
        "admin-panel/clients/",
        views.admin_clients,
        name="admin_clients",
    ),

    path(
        "admin-panel/users/create/",
        views.admin_create_user,
        name="admin_create_user",
    ),

    path(
        "admin-panel/users/<int:user_id>/edit/",
        views.admin_edit_user,
        name="admin_edit_user",
    ),

    path(
        "admin-panel/users/<int:user_id>/status/",
        views.admin_toggle_user_status,
        name="admin_toggle_user_status",
    ),

    path(
        "admin-panel/loan-products/",
        views.admin_loan_products,
        name="admin_loan_products",
    ),

    path(
        "admin-panel/loan-products/form/",
        views.admin_product_form,
        name="admin_product_form",
    ),

    path(
        "admin-panel/reports/",
        views.admin_reports,
        name="admin_reports",
    ),

    path(
        "admin-panel/audit-log/",
        views.admin_audit_log,
        name="admin_audit_log",
    ),
]