
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render

from accounting.models import BankAccount, LedgerEntry
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
    # Existing savings accounts
    accounts = SavingsAccount.objects.filter(
        client=request.client
    )

    balance = accounts.aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0.00")

    # Regular bank accounts (separate from savings)
    bank_accounts = BankAccount.objects.filter(
        client=request.client
    ).order_by("account_number")

    bank_balance = bank_accounts.aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0.00")

    # Recent transactions involving regular bank accounts
    bank_transactions = (
        LedgerEntry.objects
        .filter(bank_account__client=request.client)
        .select_related("bank_account", "loan")
        .order_by("-created_at", "-id")[:20]
    )

    loans = Loan.objects.filter(
        client=request.client
    ).select_related("product").order_by("-applied_at")

    context = {
        "balance": balance,
        "accounts": accounts,
        "bank_accounts": bank_accounts,
        "bank_balance": bank_balance,
        "bank_transactions": bank_transactions,
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
