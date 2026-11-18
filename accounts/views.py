from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .decorators import role_required

@login_required
def home(request):
    return redirect("portal_home" if request.user.role.name == "client" else "staff_home")

@role_required("client")
def portal_home(request):
    return render(request, "portal/home.html")

@role_required("admin", "loan_officer", "staff")
def staff_home(request):
    return render(request, "staff/home.html")


@role_required("client")
def my_loans(request):
    return render(request, "portal/loans.html")

@role_required("client")
def savings_history(request):
    return render(request, "portal/savings.html")

@role_required("client")
def notifications(request):
    return render(request, "portal/notifications.html")

@role_required("client")
def apply_loan(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("portal_home")
    return render(request, "portal/apply_loan.html")


@role_required("staff")
def staff_clients(request):
    return render(request, "staff/clients.html")

@role_required("staff")
def staff_client_detail(request):
    return render(request, "staff/client_detail.html")

@role_required("staff")
def staff_payments(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("staff_payments")
    return render(request, "staff/payments.html")

@role_required("staff")
def staff_savings(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("staff_savings")
    return render(request, "staff/savings.html")


@role_required("loan_officer")
def loan_applications(request):
    return render(request, "officer/applications.html")

@role_required("loan_officer")
def loan_application_detail(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("loan_applications")
    return render(request, "officer/application_detail.html")


@role_required("admin")
def admin_users(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("admin_users")
    return render(request, "adminpanel/users.html")

@role_required("admin")
def admin_loan_products(request):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect("admin_loan_products")
    return render(request, "adminpanel/loan_products.html")

@role_required("admin")
def admin_reports(request):
    return render(request, "adminpanel/reports.html")

@role_required("admin")
def admin_audit_log(request):
    return render(request, "adminpanel/audit_log.html")