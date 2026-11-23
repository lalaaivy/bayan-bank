from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError
from accounting.services import (
    deposit_to_bank,
    withdraw_from_bank,
    transfer_between_banks,
)
from audit.services import log


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


@role_required("admin")
@require_POST
def admin_toggle_bank_account_status(request, account_id):
    with transaction.atomic():
        account = get_object_or_404(
            BankAccount.objects.select_for_update(),
            pk=account_id,
        )

        if account.status == BankAccount.Status.ACTIVE:
            account.status = BankAccount.Status.FROZEN
            action = "freeze_bank_account"
            status_message = "frozen"

        elif account.status == BankAccount.Status.FROZEN:
            account.status = BankAccount.Status.ACTIVE
            action = "unfreeze_bank_account"
            status_message = "unfrozen"

        else:
            messages.error(
                request,
                "Closed bank accounts cannot be frozen or unfrozen.",
            )
            return redirect("bank_transactions")

        account.save(update_fields=["status"])
        log(request.user, action, account)

    messages.success(
        request,
        f"Bank account {account.account_number} successfully {status_message}.",
    )

    return redirect("bank_transactions")


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