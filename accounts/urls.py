from django.contrib.auth import views as auth_views
from django.urls import path

from loans import views as loan_views
from savings import views as savings_views

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("portal/", views.portal_home, name="portal_home"),
    path("staff/", views.staff_home, name="staff_home"),

    # client portal (loans and savings use the real views)
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

    # registration
    path("register/", views.register, name="register"),
    path("register/complete-profile/", views.complete_profile, name="complete_profile"),

    # role homes
    path("officer/", views.officer_home, name="officer_home"),
    path("admin-panel/", views.admin_home, name="admin_home"),

    # staff
    path("staff/clients/", views.staff_clients, name="staff_clients"),
    path("staff/clients/detail/", views.staff_client_detail, name="staff_client_detail"),
    path("staff/clients/add/", views.staff_add_client, name="staff_add_client"),
    path("staff/clients/verify/", views.verify_clients, name="verify_clients"),
    path("staff/clients/verify/<int:client_id>/", views.verify_client_detail, name="verify_client_detail"),
    path("staff/clients/document/<int:doc_id>/<str:side>/", views.client_document_file, name="client_document_file"),
    path("staff/payments/", views.staff_payments, name="staff_payments"),
    path("staff/payments/history/", views.staff_payment_history, name="staff_payment_history"),
    path("staff/payments/receipt/", views.staff_receipt, name="staff_receipt"),
    path("staff/savings/", views.staff_savings, name="staff_savings"),
    path("staff/loans/release/", views.release_loans, name="release_loans"),
    path("staff/loans/release/confirm/", views.confirm_loan_release, name="confirm_loan_release"),

    # loan officer
    path("officer/applications/", views.loan_applications, name="loan_applications"),
    path("officer/applications/detail/", views.loan_application_detail, name="loan_application_detail"),
    path("officer/loans/", views.officer_loans, name="officer_loans"),
    path("officer/loans/detail/", views.officer_loan_detail, name="officer_loan_detail"),

    # admin panel
    path("admin-panel/users/", views.admin_users, name="admin_users"),
    path("admin-panel/clients/", views.admin_clients, name="admin_clients"),
    path("admin-panel/users/create/", views.admin_create_user, name="admin_create_user"),
    path("admin-panel/users/edit/", views.admin_edit_user, name="admin_edit_user"),
    path("admin-panel/loan-products/", views.admin_loan_products, name="admin_loan_products"),
    path("admin-panel/loan-products/form/", views.admin_product_form, name="admin_product_form"),
    path("admin-panel/reports/", views.admin_reports, name="admin_reports"),
    path("admin-panel/audit-log/", views.admin_audit_log, name="admin_audit_log"),
]