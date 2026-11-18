from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .decorators import role_required

@login_required
def home(request):
    role = request.user.role.name
    destinations = {
        "client": "portal_home",
        "staff": "staff_home",
        "loan_officer": "officer_home",
        "admin": "admin_home",
    }
    return redirect(destinations.get(role, "login"))

@role_required("client")
def portal_home(request):
    return render(request, "portal/home.html")

@role_required("staff")
def staff_home(request):
    return render(request, "staff/home.html")

@role_required("loan_officer")
def officer_home(request):
    return render(request, "officer/home.html")

@role_required("admin")
def admin_home(request):
    return render(request, "adminpanel/home.html")


def _demo_form(request, template, destination):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect(destination)
    return render(request, template)


@role_required("client")
def my_loans(request):
    return render(request, "portal/loans.html")

@role_required("client")
def loan_detail(request):
    return render(request, "portal/loan_detail.html")

@role_required("client")
def savings_history(request):
    return render(request, "portal/savings.html")

@role_required("client")
def notifications(request):
    return render(request, "portal/notifications.html")

@role_required("client")
def apply_loan(request):
    return _demo_form(request, "portal/apply_loan.html", "apply_loan")

@role_required("client")
def client_profile(request):
    return render(request, "portal/profile.html")

@role_required("client")
def edit_client_profile(request):
    return _demo_form(request, "portal/profile_edit.html", "client_profile")

@role_required("client")
def change_password(request):
    return _demo_form(request, "portal/change_password.html", "client_profile")

def register(request):
    return _demo_form(request, "registration/register.html", "register")


@role_required("staff")
def staff_clients(request):
    return render(request, "staff/clients.html")

@role_required("staff")
def staff_add_client(request):
    return _demo_form(request, "staff/add_client.html", "staff_clients")

@role_required("staff")
def staff_client_detail(request):
    return render(request, "staff/client_detail.html")

@role_required("staff")
def staff_payments(request):
    return _demo_form(request, "staff/payments.html", "staff_payments")

@role_required("staff")
def staff_payment_history(request):
    return render(request, "staff/payment_history.html")

@role_required("staff")
def staff_savings(request):
    return _demo_form(request, "staff/savings.html", "staff_savings")


@role_required("loan_officer")
def loan_applications(request):
    applications = [
        {"reference": "APP-2026-1184", "name": "Liza Navarro", "product": "Business Loan", "amount": "150,000.00", "date": "Nov 17, 2026", "status": "Pending"},
        {"reference": "APP-2026-1182", "name": "Mark Villanueva", "product": "Personal Loan", "amount": "40,000.00", "date": "Nov 16, 2026", "status": "Approved"},
        {"reference": "APP-2026-1179", "name": "Joy Mercado", "product": "Emergency Loan", "amount": "25,000.00", "date": "Nov 14, 2026", "status": "Rejected"},
        {"reference": "APP-2026-1175", "name": "Roberto Garcia", "product": "Business Loan", "amount": "200,000.00", "date": "Nov 12, 2026", "status": "Pending"},
    ]
    status_filter = request.GET.get("status", "").title()
    if status_filter in {"Pending", "Approved", "Rejected"}:
        applications = [application for application in applications if application["status"] == status_filter]
    return render(request, "officer/applications.html", {"applications": applications, "status_filter": status_filter})

@role_required("loan_officer")
def officer_loans(request):
    return render(request, "officer/loans.html")

@role_required("loan_officer")
def loan_application_detail(request):
    return _demo_form(request, "officer/application_detail.html", "loan_applications")

@role_required("loan_officer")
def officer_loan_detail(request):
    return render(request, "officer/loan_detail.html")


@role_required("admin")
def admin_users(request):
    return render(request, "adminpanel/users.html")

@role_required("admin")
def admin_create_user(request):
    return _demo_form(request, "adminpanel/user_form.html", "admin_users")

@role_required("admin")
def admin_edit_user(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("admin_users")
    return render(request, "adminpanel/user_form.html", {"editing": True})

@role_required("admin")
def admin_loan_products(request):
    return render(request, "adminpanel/loan_products.html")

@role_required("admin")
def admin_product_form(request):
    return _demo_form(request, "adminpanel/product_form.html", "admin_loan_products")

@role_required("admin")
def admin_reports(request):
    return render(request, "adminpanel/reports.html")

@role_required("admin")
def admin_audit_log(request):
    return render(request, "adminpanel/audit_log.html")