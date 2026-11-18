
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render

from .decorators import client_required, role_required
from loans.models import Loan
from savings.models import SavingsAccount


@login_required
def home(request):
    if request.user.role.name == "client":
        return redirect("portal_home")

    return redirect("staff_home")


@client_required
def portal_home(request):
    accounts = SavingsAccount.objects.filter(
        client=request.client
    )

    balance = accounts.aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0.00")

    loans = Loan.objects.filter(
        client=request.client
    ).select_related("product").order_by("-applied_at")

    context = {
        "balance": balance,
        "accounts": accounts,
        "loans": loans,
    }

    return render(request, "portal/home.html", context)


@role_required("admin", "loan_officer", "staff")
def staff_home(request):
    accounts = (
        SavingsAccount.objects
        .select_related("client__user")
        .order_by("account_number")
    )

    context = {
        "pending_count": Loan.objects.filter(
            status=Loan.Status.PENDING
        ).count(),
        "active_count": Loan.objects.filter(
            status=Loan.Status.ACTIVE
        ).count(),
        "savings_accounts": accounts,
    }

    return render(request, "staff/home.html", context)
