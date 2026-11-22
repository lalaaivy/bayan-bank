from django.contrib.auth import views as auth_views
from django.urls import path

from loans import views as loan_views
from savings import views as savings_views

from . import views
from .role_dashboard import role_dashboard


urlpatterns = [
    # Main pages
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Main dashboards
    path("portal/", views.portal_home, name="portal_home"),
    path("staff/", role_dashboard, name="staff_home"),
    path("officer/", views.officer_home, name="officer_home"),
    path("admin-panel/", views.admin_home, name="admin_home"),

    # Client portal
    path("portal/loans/", loan_views.portal_loans, name="my_loans"),
    path("portal/savings/", savings_views.portal_savings, name="savings_history"),
    path("portal/notifications/", views.notifications, name="notifications"),
    path("portal/apply/", views.apply_loan, name="apply_loan"),
    path("portal/loans/detail/", views.loan_detail, name="loan_detail"),
    path("portal/upload-id/", views.upload_id, name="upload_id"),
    path("portal/accept-agreement/", views.accept_agreement, name="accept_agreement"),
    path("portal/profile/", views.client_profile, name="client_profile"),
    path("portal/profile/edit/", views.edit_client_profile, name="edit_client_profile"),
    path("portal/change-password/", views.change_password, name="change_password"),

    # Registration
    path("register/", views.register, name="register"),
    path("register/complete-profile/", views.complete_profile, name="complete_profile"),

    # Staff - Clients
    path("staff/clients/", views.staff_clients, name="staff_clients"),
    path(
        "staff/clients/<int:client_id>/",
        views.staff_client_detail,
        name="staff_client_detail",
    ),
    path("staff/clients/add/", views.staff_add_client, name="staff_add_client"),

    # Client verification
    path("staff/clients/verify/", views.verify_clients, name="verify_clients"),
    path(
        "staff/clients/verify/<int:client_id>/",
        views.verify_client_detail,
        name="verify_client_detail",
    ),
    path(
        "staff/clients/verify/<int:client_id>/",
        views.verify_client_detail,
        name="staff_verify_client",
    ),
    path(
        "staff/clients/document/<int:doc_id>/<str:side>/",
        views.client_document_file,
        name="client_document_file",
    ),

    # Staff - Payments and Savings
    path("staff/payments/", views.staff_payments, name="staff_payments"),
    path(
        "staff/payments/history/",
        views.staff_payment_history,
        name="staff_payment_history",
    ),
    path("staff/payments/receipt/", views.staff_receipt, name="staff_receipt"),
    path("staff/savings/", views.staff_savings, name="staff_savings"),

    # Staff - Loan Release
    path("staff/loans/release/", views.release_loans, name="release_loans"),
    path(
        "staff/loans/release/confirm/",
        views.confirm_loan_release,
        name="confirm_loan_release",
    ),

    # Loan Officer
    path("officer/applications/", views.loan_applications, name="loan_applications"),
    path(
        "officer/applications/<int:loan_id>/",
        views.loan_application_detail,
        name="loan_application_detail",
    ),
    path("officer/loans/", views.officer_loans, name="officer_loans"),
    path("officer/loans/detail/", views.officer_loan_detail, name="officer_loan_detail"),

    # Admin Panel
    path("admin-panel/users/", views.admin_users, name="admin_users"),
    path("admin-panel/clients/", views.admin_clients, name="admin_clients"),
    path("admin-panel/users/create/", views.admin_create_user, name="admin_create_user"),
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
    path("admin-panel/reports/", views.admin_reports, name="admin_reports"),
    path("admin-panel/audit-log/", views.admin_audit_log, name="admin_audit_log"),
]