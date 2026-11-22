
from django.contrib.auth.decorators import login_required
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
    bank_account = (
        BankAccount.objects.filter(
            client=request.client,
            status=BankAccount.Status.ACTIVE,
        )
        .order_by("pk")
        .first()
    )

    savings_account = (
        SavingsAccount.objects.filter(
            client=request.client,
        )
        .order_by("pk")
        .first()
    )

    bank_transactions = (
        LedgerEntry.objects.filter(
            bank_account__client=request.client
        )
        .select_related("bank_account")
        .order_by("-created_at", "-id")[:5]
    )

    loans = (
        Loan.objects.filter(client=request.client)
        .select_related("product")
        .order_by("-applied_at")
    )

    return render(
        request,
        "portal/home.html",
        {
            "bank_account": bank_account,
            "savings_account": savings_account,
            "bank_transactions": bank_transactions,
            "loans": loans,
        },
    )


@role_required("admin", "loan_officer", "staff")
def staff_home(request):
    accounts = (
        SavingsAccount.objects
        .select_related("client__user")
        .order_by("account_number")
    )

    return render(
        request,
        "staff/home.html",
        {
            "pending_count": Loan.objects.filter(
                status=Loan.Status.PENDING
            ).count(),
            "active_count": Loan.objects.filter(
                status=Loan.Status.ACTIVE
            ).count(),
            "savings_accounts": accounts,
        },
    )
