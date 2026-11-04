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