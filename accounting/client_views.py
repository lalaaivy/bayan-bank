
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import client_required
from accounting.client_services import client_bank_transfer
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError


@client_required
def client_bank_page(request):
    accounts = (
        BankAccount.objects
        .filter(client__user=request.user)
        .order_by("account_number")
    )

    transactions = (
        LedgerEntry.objects
        .filter(bank_account__client__user=request.user)
        .select_related("bank_account")
        .order_by("-created_at", "-id")[:30]
    )

    return render(
        request,
        "portal/bank_transactions.html",
        {
            "accounts": accounts,
            "transactions": transactions,
        },
    )


@client_required
@require_POST
def client_bank_transfer_view(request):
    try:
        client_bank_transfer(
            source_account_id=request.POST.get("source"),
            destination_account_number=request.POST.get(
                "destination"
            ),
            amount=request.POST.get("amount"),
            by=request.user,
        )

        messages.success(
            request,
            "Bank transfer completed successfully.",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect("client_bank_page")
