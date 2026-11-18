from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounting.models import LedgerEntry
from accounting.money import BankError
from accounts.decorators import client_required, role_required

from . import services
from .models import SavingsAccount

STAFF_VIEWERS = ("admin", "staff", "loan_officer")
CASHIERS = ("admin", "staff")   # may record deposits and withdrawals


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise Http404


# ---------- client portal ----------

@client_required
def portal_savings(request):
    accounts = request.client.savings_accounts.order_by("account_number")
    entries = (
        LedgerEntry.objects.filter(savings_account__client=request.client)
        .select_related("savings_account")[:20]
    )
    return render(request, "portal/savings.html", {"accounts": accounts, "recent_entries": entries})


@client_required
@require_POST
def portal_transfer(request):
    # The source account must belong to the logged-in client, otherwise 404.
    source = get_object_or_404(
        SavingsAccount, pk=_to_int(request.POST.get("from_account")), client=request.client
    )
    try:
        services.transfer(
            source.pk, request.POST.get("to_account_number", ""),
            request.POST.get("amount"), request.user,
        )
        messages.success(request, "Transfer completed.")
    except BankError as e:
        messages.error(request, str(e))
    return redirect("portal_savings")


# ---------- staff ----------

@role_required(*STAFF_VIEWERS)
def staff_account(request, account_id):
    account = get_object_or_404(SavingsAccount.objects.select_related("client__user"), pk=account_id)
    return render(request, "staff/savings_detail.html", {
        "account": account,
        "entries": account.ledger_entries.all()[:20],
        "can_cash": request.user.role.name in CASHIERS,
    })


def _cash_action(request, account_id, action, success_message):
    account = get_object_or_404(SavingsAccount, pk=account_id)
    try:
        action(account.pk, request.POST.get("amount"), request.user)
        messages.success(request, success_message)
    except BankError as e:
        messages.error(request, str(e))
    return redirect("staff_account", account_id=account.pk)


@role_required(*CASHIERS)
@require_POST
def staff_deposit(request, account_id):
    return _cash_action(request, account_id, services.deposit, "Deposit recorded.")


@role_required(*CASHIERS)
@require_POST
def staff_withdraw(request, account_id):
    return _cash_action(request, account_id, services.withdraw, "Withdrawal recorded.")