
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import client_required
from accounting.client_services import client_bank_transfer
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError


@client_required
def client_bank_page(request):
    account = (
        BankAccount.objects.filter(
            client=request.client,
            status=BankAccount.Status.ACTIVE,
        )
        .order_by("pk")
        .first()
    )

    transactions = (
        LedgerEntry.objects.filter(
            bank_account__client=request.client
        )
        .select_related("bank_account")
        .order_by("-created_at", "-id")[:30]
    )

    return render(
        request,
        "portal/bank_transactions.html",
        {
            "account": account,
            "transactions": transactions,
        },
    )


@client_required
@require_POST
def client_bank_transfer_view(request):
    try:
        account = BankAccount.objects.get(
            client=request.client,
            status=BankAccount.Status.ACTIVE,
        )

        client_bank_transfer(
            source_account_id=account.pk,
            destination_account_number=request.POST.get(
                "destination", ""
            ),
            amount=request.POST.get("amount"),
            by=request.user,
        )

        messages.success(
            request,
            "Bank transfer completed successfully.",
        )

    except BankAccount.DoesNotExist:
        messages.error(
            request,
            "You do not have an active regular bank account.",
        )
    except BankAccount.MultipleObjectsReturned:
        messages.error(
            request,
            "Multiple active accounts detected. Contact bank staff.",
        )
    except BankError as error:
        messages.error(request, str(error))

    return redirect("client_bank_page")
