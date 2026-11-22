
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError
from accounting.services import (
    deposit_to_bank,
    withdraw_from_bank,
    transfer_between_banks,
)


VIEW_ROLES = ("admin", "staff")
CASHIER_ROLES = ("staff",)


@role_required(*VIEW_ROLES)
def bank_transactions(request):
    accounts = (
        BankAccount.objects
        .select_related("client__user")
        .order_by("account_number")
    )

    transactions = (
        LedgerEntry.objects
        .filter(bank_account__isnull=False)
        .select_related("bank_account", "created_by")
        .order_by("-created_at", "-id")[:30]
    )

    return render(
        request,
        "staff/bank_transactions.html",
        {
            "accounts": accounts,
            "transactions": transactions,
            "can_cash": request.user.role.name in CASHIER_ROLES,
        },
    )


@role_required(*CASHIER_ROLES)
@require_POST
def bank_deposit(request):
    try:
        deposit_to_bank(
            account_id=request.POST.get("account"),
            amount=request.POST.get("amount"),
            by=request.user,
        )
        messages.success(
            request,
            "Deposit completed successfully.",
        )
    except BankError as error:
        messages.error(request, str(error))

    return redirect("bank_transactions")


@role_required(*CASHIER_ROLES)
@require_POST
def bank_withdraw(request):
    try:
        withdraw_from_bank(
            account_id=request.POST.get("account"),
            amount=request.POST.get("amount"),
            by=request.user,
        )
        messages.success(
            request,
            "Withdrawal completed successfully.",
        )
    except BankError as error:
        messages.error(request, str(error))

    return redirect("bank_transactions")


@role_required(*CASHIER_ROLES)
@require_POST
def bank_transfer(request):
    try:
        transfer_between_banks(
            source_account_id=request.POST.get("source"),
            destination_account_id=request.POST.get("destination"),
            amount=request.POST.get("amount"),
            by=request.user,
        )
        messages.success(
            request,
            "Transfer completed successfully.",
        )
    except BankError as error:
        messages.error(request, str(error))

    return redirect("bank_transactions")