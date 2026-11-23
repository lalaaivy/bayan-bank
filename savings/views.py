from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
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
    SavingsCashWithdrawalRequest,
    SavingsTransferRequest,
)


# =====================================================
# CONFIGURATION
# =====================================================

STAFF_VIEWERS = ("admin", "staff", "loan_officer")
CASHIERS = ("staff",)

ZERO_AMOUNT = Decimal("0.00")


def _is_cashier(user):
    role_name = getattr(
        getattr(user, "role", None),
        "name",
        "",
    )

    return role_name.lower() in CASHIERS


def _cash_request_account_filter(account):
    """
    Include new account-wide requests and historical
    requests linked to individual deposits.
    """
    return (
        Q(savings_account=account)
        | Q(deposit__savings_account=account)
    )


def _get_cash_request_account(withdrawal_request):
    """
    Resolve the savings account for a new or historical request.
    """
    if withdrawal_request.savings_account_id:
        return withdrawal_request.savings_account_id

    if withdrawal_request.deposit_id:
        return withdrawal_request.deposit.savings_account_id

    return None


# =====================================================
# SAVINGS BALANCE RECONCILIATION
# =====================================================

def _remaining_deposit_principal(deposit):
    if deposit.status == SavingsDeposit.Status.RELEASED:
        return ZERO_AMOUNT

    if deposit.remaining_principal is None:
        return deposit.amount

    return deposit.remaining_principal


def _attach_savings_reconciliation(accounts, deposits=None):
    """
    Attach display-only reconciliation values to savings accounts.

    No financial records or balances are modified.
    """
    if deposits is None:
        deposits = []

        for account in accounts:
            deposits.extend(account.deposits.all())

    tracked_by_account = {}

    for deposit in deposits:
        account_id = deposit.savings_account_id

        tracked_by_account[account_id] = (
            tracked_by_account.get(account_id, ZERO_AMOUNT)
            + _remaining_deposit_principal(deposit)
        )

    for account in accounts:
        tracked = tracked_by_account.get(
            account.pk,
            ZERO_AMOUNT,
        )

        balance = account.balance or ZERO_AMOUNT
        difference = balance - tracked

        account.tracked_deposit_balance = tracked
        account.unallocated_balance = max(
            difference,
            ZERO_AMOUNT,
        )
        account.balance_difference = difference
        account.has_balance_discrepancy = difference < ZERO_AMOUNT

    return accounts


# =====================================================
# SHARED SAVINGS DISPLAY HELPERS
# =====================================================

def _prepare_deposit(deposit, today):
    remaining = _remaining_deposit_principal(deposit)

    deposit.available_principal = remaining
    deposit.total_release = remaining + deposit.interest_amount

    deposit.is_matured = (
        deposit.status != SavingsDeposit.Status.RELEASED
        and deposit.maturity_date <= today
    )

    deposit.is_released = (
        deposit.status == SavingsDeposit.Status.RELEASED
        or remaining <= ZERO_AMOUNT
    )

    transfer_requests = list(deposit.transfer_requests.all())

    deposit.pending_transfer_request = any(
        item.status == SavingsTransferRequest.Status.PENDING
        for item in transfer_requests
    )

    deposit.latest_transfer_request = (
        transfer_requests[0] if transfer_requests else None
    )

    early_requests = list(deposit.early_withdrawal_requests.all())

    deposit.pending_early_withdrawal = any(
        item.status == SavingsEarlyWithdrawalRequest.Status.PENDING
        for item in early_requests
    )

    # Only historical deposit-linked cash requests belong here.
    cash_requests = list(deposit.cash_withdrawal_requests.all())

    deposit.pending_cash_withdrawal = any(
        item.status in (
            SavingsCashWithdrawalRequest.Status.PENDING,
            SavingsCashWithdrawalRequest.Status.APPROVED,
        )
        for item in cash_requests
    )

    deposit.latest_cash_withdrawal_request = (
        cash_requests[0] if cash_requests else None
    )

    return deposit

def _attach_account_cash_requests(accounts, cash_requests):
    """
    Attach account-wide cash withdrawal information for templates.
    Includes historical requests linked to individual deposits.
    """
    requests_by_account = {}

    for withdrawal_request in cash_requests:
        account_id = _get_cash_request_account(withdrawal_request)

        if account_id is None:
            continue

        requests_by_account.setdefault(account_id, []).append(
            withdrawal_request
        )

    for account in accounts:
        account_requests = requests_by_account.get(account.pk, [])

        # Use a separate attribute. Do not overwrite Django's related manager.
        account.cash_withdrawal_request_list = account_requests

        has_pending = any(
            item.status in (
                SavingsCashWithdrawalRequest.Status.PENDING,
                SavingsCashWithdrawalRequest.Status.APPROVED,
            )
            for item in account_requests
        )

        account.pending_cash_withdrawal = has_pending
        account.has_pending_cash_withdrawal = has_pending

        account.latest_cash_withdrawal_request = (
            account_requests[0] if account_requests else None
        )

    return accounts

def _get_client_savings_entries(client):
    return (
        LedgerEntry.objects
        .filter(
            Q(bank_account__client=client)
            | Q(savings_account__client=client)
        )
        .select_related(
            "bank_account",
            "savings_account",
            "loan",
        )
        .order_by("-created_at", "-id")[:20]
    )


# =====================================================
# CLIENT PORTAL
# =====================================================

@client_required
def portal_savings(request):
    """Display the client's savings accounts, deposits, and requests."""

    accounts = list(
        SavingsAccount.objects
        .filter(client=request.client)
        .annotate(
            total_interest=Sum("deposits__interest_amount")
        )
        .order_by("account_number")
    )

    bank_account = BankAccount.objects.filter(
        client=request.client,
        status=BankAccount.Status.ACTIVE,
    ).first()

    deposits = list(
        SavingsDeposit.objects
        .filter(savings_account__client=request.client)
        .select_related("savings_account")
        .prefetch_related(
            "early_withdrawal_requests",
            "cash_withdrawal_requests",
            "transfer_requests",
        )
        .order_by("-deposited_at")
    )

    today = timezone.localdate()

    for deposit in deposits:
        _prepare_deposit(deposit, today)

    _attach_savings_reconciliation(accounts, deposits)

    withdrawal_requests = (
        SavingsEarlyWithdrawalRequest.objects
        .filter(deposit__savings_account__client=request.client)
        .select_related(
            "deposit",
            "reviewed_by",
        )
        .order_by("-requested_at")
    )

    cash_withdrawal_requests = list(
        SavingsCashWithdrawalRequest.objects
        .filter(
            Q(savings_account__client=request.client)
            | Q(deposit__savings_account__client=request.client)
        )
        .select_related(
            "savings_account",
            "deposit",
            "deposit__savings_account",
            "reviewed_by",
            "paid_by",
            "payout_ledger_entry",
        )
        .order_by("-requested_at")
    )

    _attach_account_cash_requests(accounts, cash_withdrawal_requests)

    transfer_requests = (
        SavingsTransferRequest.objects
        .filter(deposit__savings_account__client=request.client)
        .select_related(
            "deposit",
            "reviewed_by",
        )
        .order_by("-requested_at")
    )

    entries = _get_client_savings_entries(request.client)

    return render(
        request,
        "portal/savings.html",
        {
            "accounts": accounts,
            "bank_account": bank_account,
            "deposits": deposits,
            "withdrawal_requests": withdrawal_requests,
            "cash_withdrawal_requests": cash_withdrawal_requests,
            "transfer_requests": transfer_requests,
            "entries": entries,
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

    except BankError as error:
        messages.error(request, str(error))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_transfer(request):
    """Transfer money from the regular account into locked savings."""

    bank_account = BankAccount.objects.filter(
        client=request.client,
        status=BankAccount.Status.ACTIVE,
    ).first()

    savings_account = SavingsAccount.objects.filter(
        client=request.client,
        status=SavingsAccount.Status.ACTIVE,
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

    except BankError as error:
        messages.error(request, str(error))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_request_savings_transfer(request, deposit_id):
    deposit = get_object_or_404(
        SavingsDeposit.objects.select_related("savings_account"),
        pk=deposit_id,
        savings_account__client=request.client,
    )

    try:
        transfer_request = services.request_savings_transfer(
            deposit.pk,
            request.user,
        )

        messages.success(
            request,
            f"Your request #{transfer_request.pk} to transfer matured "
            "savings to your regular bank account was submitted. "
            "It is waiting for staff approval.",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_release_matured(request, deposit_id):
    return portal_request_savings_transfer(request, deposit_id)


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
            "was submitted. It is pending staff review.",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect("portal_savings")


@client_required
@require_POST
def portal_request_cash_withdrawal(
    request,
    deposit_id=None,
    account_id=None,
):
    """
    Submit a withdrawal request against the total SavingsAccount balance.

    The existing URL parameter deposit_id is retained for compatibility.
    Its value is treated as the SavingsAccount ID for this workflow.

    Cash withdrawal requests are not restricted by individual deposit
    maturity dates.
    """
    savings_account_id = account_id or deposit_id

    if not savings_account_id:
        messages.error(request, "Savings account not found.")
        return redirect("portal_savings")

    savings_account = get_object_or_404(
        SavingsAccount,
        pk=savings_account_id,
        client=request.client,
    )

    try:
        withdrawal_request = services.request_savings_cash_withdrawal(
            savings_account.pk,
            request.POST.get("amount"),
            request.POST.get("reason", ""),
            request.user,
        )

        messages.success(
            request,
            f"Your cash withdrawal request #{withdrawal_request.pk} "
            f"for ₱{withdrawal_request.amount:,.2f} was submitted. "
            "Please wait for staff review. No funds have been deducted.",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect("portal_savings")


# =====================================================
# STAFF SAVINGS ACCOUNT LIST AND DETAILS
# =====================================================

@role_required(*STAFF_VIEWERS)
def staff_savings(request):
    accounts = list(
        SavingsAccount.objects
        .select_related("client__user")
        .prefetch_related("deposits")
        .order_by("-opened_at")
    )

    _attach_savings_reconciliation(accounts)

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
        client=account.client,
        status=BankAccount.Status.ACTIVE,
    ).first()

    deposits = list(
        account.deposits
        .select_related("released_by")
        .prefetch_related(
            "early_withdrawal_requests",
            "cash_withdrawal_requests",
            "transfer_requests",
        )
        .order_by("-deposited_at")
    )

    today = timezone.localdate()

    for deposit in deposits:
        _prepare_deposit(deposit, today)

    _attach_savings_reconciliation([account], deposits)

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

    cash_withdrawal_requests = list(
        SavingsCashWithdrawalRequest.objects
        .filter(_cash_request_account_filter(account))
        .select_related(
            "savings_account",
            "deposit",
            "requested_by",
            "reviewed_by",
            "paid_by",
            "payout_ledger_entry",
        )
        .order_by("-requested_at")
    )

    _attach_account_cash_requests(
        [account],
        cash_withdrawal_requests,
    )

    transfer_requests = (
        SavingsTransferRequest.objects
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

    can_review = _is_cashier(request.user)

    return render(
        request,
        "staff/savings_detail.html",
        {
            "account": account,
            "bank_account": bank_account,
            "entries": entries,
            "deposits": deposits,
            "withdrawal_requests": withdrawal_requests,
            "cash_withdrawal_requests": cash_withdrawal_requests,
            "transfer_requests": transfer_requests,
            "can_cash": can_review,
            "can_post_interest": False,
            "can_review_withdrawals": can_review,
            "can_review_cash_withdrawals": can_review,
            "can_review_transfers": can_review,
            "today": today,
        },
    )


# =====================================================
# STAFF PHYSICAL SAVINGS DEPOSIT
# =====================================================

@role_required(*CASHIERS)
@require_POST
def staff_deposit(request, account_id):
    savings_account = get_object_or_404(
        SavingsAccount.objects.select_related("client"),
        pk=account_id,
    )

    try:
        result = services.staff_savings_cash_deposit(
            savings_account.pk,
            request.POST.get("amount"),
            request.user,
            term_months=request.POST.get("term_months", 3),
        )

        deposit = result["deposit"]

        messages.success(
            request,
            f"Physical cash deposit of ₱{deposit.amount:,.2f} "
            f"recorded successfully. "
            f"Term: {deposit.term_months} months. "
            f"Maturity date: {deposit.maturity_date}. "
            f"Reference: {result['reference']}",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect(
        "staff_account",
        account_id=savings_account.pk,
    )


# =====================================================
# STAFF PHYSICAL CASH WITHDRAWAL REVIEW
# =====================================================

def _review_cash_withdrawal(request, request_id, approved):
    withdrawal_statuses = [
        SavingsCashWithdrawalRequest.Status.PENDING,
    ]

    # Allow staff to process an already-approved legacy request.
    # Rejections remain restricted to pending requests.
    if approved:
        withdrawal_statuses.append(
            SavingsCashWithdrawalRequest.Status.APPROVED
        )

    withdrawal_request = get_object_or_404(
        SavingsCashWithdrawalRequest.objects.select_related(
            "savings_account",
            "deposit",
            "deposit__savings_account",
        ),
        pk=request_id,
        status__in=withdrawal_statuses,
    )

    account_id = _get_cash_request_account(withdrawal_request)

    if not account_id:
        messages.error(
            request,
            "This withdrawal request has no associated savings account.",
        )
        return redirect("staff_savings")

    try:
        result = services.review_savings_cash_withdrawal_request(
            request_id=withdrawal_request.pk,
            approved=approved,
            reviewed_by=request.user,
            staff_notes=request.POST.get("staff_notes", ""),
        )

        if approved:
            messages.success(
                request,
                f"Withdrawal request #{withdrawal_request.pk} processed. "
                f"₱{result['amount']:,.2f} has been transferred "
                "to the client's regular bank account. "
                f"Transfer reference: {result['reference']}.",
            )
        else:
            messages.success(
                request,
                f"Withdrawal request #{withdrawal_request.pk} rejected. "
                "No funds were transferred.",
            )

    except BankError as error:
        messages.error(request, str(error))

    return redirect(
        "staff_account",
        account_id=account_id,
    )
@role_required(*CASHIERS)
@require_POST
def staff_withdraw(request, account_id):
    """Compatibility endpoint that approves a pending request only."""

    savings_account = get_object_or_404(
        SavingsAccount,
        pk=account_id,
    )

    request_id = request.POST.get("request_id")

    if not request_id:
        messages.error(
            request,
            "Select a pending client cash withdrawal request to review.",
        )
        return redirect(
            "staff_account",
            account_id=savings_account.pk,
        )

    withdrawal_request = get_object_or_404(
        SavingsCashWithdrawalRequest.objects.filter(
            _cash_request_account_filter(savings_account)
        ),
        pk=request_id,
    )

    return _review_cash_withdrawal(
        request,
        withdrawal_request.pk,
        approved=True,
    )


@role_required(*CASHIERS)
@require_POST
def staff_approve_cash_withdrawal(request, request_id):
    return _review_cash_withdrawal(
        request,
        request_id,
        approved=True,
    )


@role_required(*CASHIERS)
@require_POST
def staff_reject_cash_withdrawal(request, request_id):
    return _review_cash_withdrawal(
        request,
        request_id,
        approved=False,
    )


# =====================================================
# STAFF PHYSICAL CASH PAYOUT CONFIRMATION
# =====================================================
@role_required(*CASHIERS)
@require_POST
def staff_confirm_cash_withdrawal_payout(request, request_id):
    """
    Legacy endpoint.

    Cash payout confirmation is disabled because staff approval
    now transfers savings directly to the client's regular account.
    """
    messages.error(
        request,
        "This cash payout action is no longer available. "
        "Savings withdrawals are transferred automatically "
        "when staff approves the request.",
    )

    withdrawal_request = get_object_or_404(
        SavingsCashWithdrawalRequest.objects.select_related(
            "savings_account",
            "deposit",
            "deposit__savings_account",
        ),
        pk=request_id,
    )

    account_id = _get_cash_request_account(withdrawal_request)

    if not account_id:
        return redirect("staff_savings")

    return redirect(
        "staff_account",
        account_id=account_id,
    )

# =====================================================
# STAFF INTEREST POSTING
# =====================================================

@role_required(*CASHIERS)
@require_POST
def staff_post_interest(request, account_id):
    get_object_or_404(
        SavingsAccount,
        pk=account_id,
    )

    messages.error(
        request,
        "Monthly account-wide interest posting is disabled. "
        "Interest is calculated separately for each savings deposit "
        "when an eligible amount is released.",
    )

    return redirect(
        "staff_account",
        account_id=account_id,
    )


# =====================================================
# STAFF EARLY-WITHDRAWAL REVIEW
# =====================================================

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

    except BankError as error:
        messages.error(request, str(error))

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


# =====================================================
# STAFF MATURED SAVINGS TRANSFER REVIEW
# =====================================================

def _review_savings_transfer(request, request_id, approved):
    transfer_request = get_object_or_404(
        SavingsTransferRequest.objects.select_related(
            "deposit",
            "deposit__savings_account",
        ),
        pk=request_id,
        status=SavingsTransferRequest.Status.PENDING,
    )

    account_id = transfer_request.deposit.savings_account_id

    try:
        result = services.review_savings_transfer_request(
            request_id=transfer_request.pk,
            approved=approved,
            reviewed_by=request.user,
            staff_notes=request.POST.get("staff_notes", ""),
        )

        if approved:
            messages.success(
                request,
                f"Savings transfer request approved. "
                f"₱{result['total_release']:,.2f} "
                "was transferred to the client's regular bank account.",
            )
        else:
            messages.success(
                request,
                "Savings transfer request rejected. "
                "The matured savings deposit remains in the savings account.",
            )

    except BankError as error:
        messages.error(request, str(error))

    return redirect(
        "staff_account",
        account_id=account_id,
    )


@role_required(*CASHIERS)
@require_POST
def staff_approve_savings_transfer(request, request_id):
    return _review_savings_transfer(
        request,
        request_id,
        approved=True,
    )


@role_required(*CASHIERS)
@require_POST
def staff_reject_savings_transfer(request, request_id):
    return _review_savings_transfer(
        request,
        request_id,
        approved=False,
    )