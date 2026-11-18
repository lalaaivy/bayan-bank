from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("portal/", views.portal_home, name="portal_home"),
    path("staff/", views.staff_home, name="staff_home"),
    path("portal/loans/", views.my_loans, name="my_loans"),
    path("portal/savings/", views.savings_history, name="savings_history"),
    path("portal/notifications/", views.notifications, name="notifications"),
    path("portal/apply/", views.apply_loan, name="apply_loan"),
    path("staff/clients/", views.staff_clients, name="staff_clients"),
    path("staff/clients/detail/", views.staff_client_detail, name="staff_client_detail"),
    path("staff/payments/", views.staff_payments, name="staff_payments"),
    path("staff/savings/", views.staff_savings, name="staff_savings"),
    path("officer/applications/", views.loan_applications, name="loan_applications"),
    path("officer/applications/detail/", views.loan_application_detail, name="loan_application_detail"),
    path("admin/users/", views.admin_users, name="admin_users"),
    path("admin/loan-products/", views.admin_loan_products, name="admin_loan_products"),
    path("admin/reports/", views.admin_reports, name="admin_reports"),
    path("admin/audit-log/", views.admin_audit_log, name="admin_audit_log"),
]


