
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError
from accounts.decorators import client_required, role_required

from . import services
from .models import (
    SavingsAccount,
    SavingsDeposit,
    SavingsEarlyWithdrawalRequest,
)


STAFF_VIEWERS = ("admin", "staff", "loan_officer")
CASHIERS = ("admin", "staff")


def _is_cashier(user):
    role_name = getattr(
        getattr(user, "role", None),
        "name",
        "",
    )
    return role_name.lower() in CASHIERS


# ---------- Client portal ----------

@client_required
def portal_savings(request):
    accounts = (
        SavingsAccount.objects
        .filter(client=request.client)
        .annotate(
            total_interest=Sum("deposits__interest_amount")
        )
        .order_by("account_number")
    )

    bank_account = BankAccount.objects.filter(
        client=request.client
    ).first()

    deposits = list(
        SavingsDeposit.objects
        .filter(savings_account__client=request.client)
        .select_related("savings_account")
        .prefetch_related("early_withdrawal_requests")
        .order_by("-deposited_at")
    )

    today = timezone.localdate()

    for deposit in deposits:
        deposit.total_release = (
            deposit.amount + deposit.interest_amount
        )

        deposit.is_matured = (
            deposit.status != SavingsDeposit.Status.RELEASED
            and deposit.maturity_date <= today
        )

        deposit.is_released = (
            deposit.status == SavingsDeposit.Status.RELEASED
        )

    withdrawal_requests = (
        SavingsEarlyWithdrawalRequest.objects
        .filter(deposit__savings_account__client=request.client)
        .select_related(
            "deposit",
            "reviewed_by",
        )
        .order_by("-requested_at")
    )

    entries = (
        LedgerEntry.objects
        .filter(
            Q(bank_account__client=request.client)
            | Q(savings_account__client=request.client)
        )
        .select_related(
            "bank_account",
            "savings_account",
            "loan",
        )
        .order_by("-created_at", "-id")[:20]
    )

    return render(
        request,
        "portal/savings.html",
        {
            "accounts": accounts,
            "bank_account": bank_account,
            "deposits": deposits,
            "withdrawal_requests": withdrawal_requests,
            "recent_entries": entries,
            "today": today,
        },
    )


@client_required
@require_POST
def portal_open_account(request):
    if request.client.verification_status != "active":
        messages.error(
            request,
            "Your account must be verified before you can open a savings account.",
        )
        return redirect("portal_savings")

    try:
        account = services.open_account(
            request.client,
            request.user,
        )

        messages.success(
            request,
            f"Your new savings account was opened successfully. "
            f"Account number: {account.account_number}",
        )

    except BankError as e:
        messages.error(request, str(e))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_transfer(request):
    bank_account = BankAccount.objects.filter(
        client=request.client
    ).first()

    savings_account = SavingsAccount.objects.filter(
        client=request.client
    ).first()

    if bank_account is None:
        messages.error(
            request,
            "You do not have a regular bank account available for transfers.",
        )
        return redirect("portal_savings")

    if savings_account is None:
        messages.error(
            request,
            "Open a savings account before making a transfer.",
        )
        return redirect("portal_savings")

    try:
        result = services.transfer_to_savings(
            bank_account.pk,
            savings_account.pk,
            request.POST.get("amount"),
            request.user,
            term_months=request.POST.get("term_months", 3),
        )

        deposit = result["deposit"]

        messages.success(
            request,
            f"Transfer of ₱{deposit.amount:,.2f} completed successfully. "
            f"Term: {deposit.term_months} months. "
            f"Maturity date: {deposit.maturity_date}. "
            f"Reference: {result['reference']}",
        )

    except BankError as e:
        messages.error(request, str(e))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_release_matured(request, deposit_id):
    deposit = get_object_or_404(
        SavingsDeposit.objects.select_related("savings_account"),
        pk=deposit_id,
        savings_account__client=request.client,
    )

    try:
        result = services.release_matured_deposit(
            deposit.pk,
            request.user,
        )

        messages.success(
            request,
            f"Savings deposit released successfully. "
            f"Principal: ₱{result['principal']:,.2f}; "
            f"interest: ₱{result['interest']:,.2f}; "
            f"total credited to your regular account: "
            f"₱{result['total_release']:,.2f}.",
        )

    except BankError as e:
        messages.error(request, str(e))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_request_early_withdrawal(request, deposit_id):
    deposit = get_object_or_404(
        SavingsDeposit.objects.select_related("savings_account"),
        pk=deposit_id,
        savings_account__client=request.client,
    )

    try:
        withdrawal_request = services.request_early_withdrawal(
            deposit.pk,
            request.POST.get("reason"),
            request.user,
        )

        messages.success(
            request,
            f"Your early withdrawal request #{withdrawal_request.pk} "
            "was submitted. It is pending physical-branch staff review.",
        )

    except BankError as e:
        messages.error(request, str(e))

    return redirect("portal_savings")


# ---------- staff savings accounts ----------

@role_required(*STAFF_VIEWERS)
def staff_savings(request):
    accounts = (
        SavingsAccount.objects
        .select_related("client__user")
        .order_by("-opened_at")
    )

    return render(
        request,
        "staff/savings_list.html",
        {"accounts": accounts},
    )


@role_required(*STAFF_VIEWERS)
def staff_account(request, account_id):
    account = get_object_or_404(
        SavingsAccount.objects.select_related("client__user"),
        pk=account_id,
    )

    bank_account = BankAccount.objects.filter(
        client=account.client
    ).first()

    deposits = list(
        account.deposits
        .select_related("released_by")
        .prefetch_related("early_withdrawal_requests")
        .order_by("-deposited_at")
    )

    today = timezone.localdate()

    for deposit in deposits:
        deposit.total_release = (
            deposit.amount + deposit.interest_amount
        )

        deposit.is_matured = (
            deposit.status != SavingsDeposit.Status.RELEASED
            and deposit.maturity_date <= today
        )

        deposit.is_released = (
            deposit.status == SavingsDeposit.Status.RELEASED
        )

    withdrawal_requests = (
        SavingsEarlyWithdrawalRequest.objects
        .filter(deposit__savings_account=account)
        .select_related(
            "deposit",
            "requested_by",
            "reviewed_by",
        )
        .order_by("-requested_at")
    )

    entries = (
        LedgerEntry.objects
        .filter(savings_account=account)
        .select_related("created_by")
        .order_by("-created_at", "-id")[:20]
    )

    return render(
        request,
        "staff/savings_detail.html",
        {
            "account": account,
            "bank_account": bank_account,
            "entries": entries,
            "deposits": deposits,
            "withdrawal_requests": withdrawal_requests,
            "can_cash": _is_cashier(request.user),
            "can_post_interest": False,
            "can_review_withdrawals": _is_cashier(request.user),
            "today": today,
        },
    )


# ---------- staff cash deposits ----------

@role_required(*CASHIERS)
@require_POST
def staff_deposit(request, account_id):
    savings_account = get_object_or_404(
        SavingsAccount.objects.select_related("client"),
        pk=account_id,
    )

    bank_account = BankAccount.objects.filter(
        client=savings_account.client
    ).first()

    if bank_account is None:
        messages.error(
            request,
            "This client does not have a regular bank account.",
        )
        return redirect(
            "staff_account",
            account_id=savings_account.pk,
        )

    try:
        entry = services.staff_cash_deposit(
            bank_account.pk,
            request.POST.get("amount"),
            request.user,
        )

        messages.success(
            request,
            f"Cash deposit of ₱{entry.amount:,.2f} "
            "credited to the client's regular bank account. "
            f"Reference: {entry.reference}",
        )

    except BankError as e:
        messages.error(request, str(e))

    return redirect(
        "staff_account",
        account_id=savings_account.pk,
    )


@role_required(*CASHIERS)
@require_POST
def staff_withdraw(request, account_id):
    get_object_or_404(SavingsAccount, pk=account_id)

    messages.error(
        request,
        "Direct savings withdrawals are not allowed. "
        "An early withdrawal request must be reviewed and approved.",
    )

    return redirect(
        "staff_account",
        account_id=account_id,
    )


@role_required(*CASHIERS)
@require_POST
def staff_post_interest(request, account_id):
    get_object_or_404(SavingsAccount, pk=account_id)

    messages.error(
        request,
        "Monthly account-wide interest posting is disabled. "
        "Interest is calculated separately for each savings deposit "
        "when it is released.",
    )

    return redirect(
        "staff_account",
        account_id=account_id,
    )


# ---------- staff early-withdrawal review ----------

def _review_early_withdrawal(request, request_id, approved):
    withdrawal_request = get_object_or_404(
        SavingsEarlyWithdrawalRequest.objects.select_related(
            "deposit",
            "deposit__savings_account",
        ),
        pk=request_id,
        status=SavingsEarlyWithdrawalRequest.Status.PENDING,
    )

    account_id = withdrawal_request.deposit.savings_account_id

    try:
        result = services.review_early_withdrawal_request(
            request_id=withdrawal_request.pk,
            approved=approved,
            reviewed_by=request.user,
            staff_notes=request.POST.get("staff_notes", ""),
            branch_reference=request.POST.get("branch_reference", ""),
        )

        if approved:
            messages.success(
                request,
                f"Early withdrawal approved. "
                f"₱{result['total_release']:,.2f} "
                "was credited to the client's regular bank account.",
            )
        else:
            messages.success(
                request,
                "Early withdrawal request rejected. "
                "The client's savings deposit remains locked.",
            )

    except BankError as e:
        messages.error(request, str(e))

    return redirect(
        "staff_account",
        account_id=account_id,
    )


@role_required(*CASHIERS)
@require_POST
def staff_approve_early_withdrawal(request, request_id):
    return _review_early_withdrawal(
        request,
        request_id,
        approved=True,
    )


@role_required(*CASHIERS)
@require_POST
def staff_reject_early_withdrawal(request, request_id):
    return _review_early_withdrawal(
        request,
        request_id,
        approved=False,
    )
