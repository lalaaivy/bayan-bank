import calendar
import secrets
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from clients.services import client_has_active_security_freeze
from notifications.models import Notification

from .models import (
    SavingsAccount,
    SavingsDeposit,
    SavingsEarlyWithdrawalRequest,
    SavingsCashWithdrawalRequest,
    SavingsTransferRequest,
)


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
DEFAULT_ANNUAL_INTEREST_RATE = Decimal("2.00")
SUPPORTED_TERMS = (3, 6, 12)

INTERNAL_NOTIFICATION_ROLES = (
    Role.ADMIN,
    Role.LOAN_OFFICER,
    Role.STAFF,
)

NOTIFICATION_KINDS = {
    "SAVINGS_OPENED": "savings_opened",
    "CASH_DEPOSIT": "cash_deposit",
    "CASH_WITHDRAWAL": "cash_withdrawal",
    "SAVINGS_TRANSFER": "savings_transfer",
    "SAVINGS_RELEASED": "savings_released",
    "EARLY_WITHDRAWAL_REQUESTED": "early_wd_requested",
    "EARLY_WITHDRAWAL_APPROVED": "early_wd_approved",
    "EARLY_WITHDRAWAL_REJECTED": "early_wd_rejected",
    "TRANSFER_REQUESTED": "savings_transfer_requested",
    "TRANSFER_APPROVED": "savings_transfer_approved",
    "TRANSFER_REJECTED": "savings_transfer_rejected",
    "CASH_WITHDRAWAL_REQUESTED": "savings_cash_wd_requested",
    "CASH_WITHDRAWAL_APPROVED": "savings_cash_wd_approved",
    "CASH_WITHDRAWAL_REJECTED": "savings_cash_wd_rejected",
}


# ==========================================
# SECURITY FREEZE CHECK
# ==========================================

def _require_no_security_freeze(client_id):
    if client_has_active_security_freeze(client_id):
        raise BankError(
            "This client's accounts are under a security restriction. "
            "Financial transactions are currently unavailable."
        )


# ==========================================
# NOTIFICATIONS
# ==========================================

def _notify_savings_event(
    client,
    kind,
    client_message,
    staff_message=None,
    exclude_user=None,
):
    notifications = []

    if client and client.user_id:
        notifications.append(
            Notification(
                user=client.user,
                kind=kind,
                message=client_message[:255],
            )
        )

    internal_users = User.objects.filter(
        is_active=True,
        role__name__in=INTERNAL_NOTIFICATION_ROLES,
    )

    if client and client.user_id:
        internal_users = internal_users.exclude(pk=client.user_id)

    if exclude_user is not None:
        internal_users = internal_users.exclude(pk=exclude_user.pk)

    internal_message = (staff_message or client_message)[:255]

    notifications.extend(
        Notification(
            user=user,
            kind=kind,
            message=internal_message,
        )
        for user in internal_users
    )

    if notifications:
        Notification.objects.bulk_create(notifications)


# ==========================================
# ACCOUNT LOCKING AND VALIDATION
# ==========================================

def _lock_savings_account(account_id):
    try:
        return (
            SavingsAccount.objects
            .select_for_update()
            .select_related("client", "client__user")
            .get(pk=int(account_id))
        )
    except (SavingsAccount.DoesNotExist, TypeError, ValueError):
        raise BankError("Savings account not found.")


def _lock_bank_account(account_id):
    try:
        return (
            BankAccount.objects
            .select_for_update()
            .select_related("client", "client__user")
            .get(pk=int(account_id))
        )
    except (BankAccount.DoesNotExist, TypeError, ValueError):
        raise BankError("Bank account not found.")


def _require_active(account):
    if account.status != SavingsAccount.Status.ACTIVE:
        raise BankError(
            f"Savings account {account.account_number} is {account.status}."
        )


def _require_active_bank_account(account):
    if account.status != BankAccount.Status.ACTIVE:
        raise BankError(
            f"Bank account {account.account_number} is {account.status}."
        )


def _require_owner(account, user):
    if not user or not user.is_authenticated:
        raise BankError("Authentication is required.")

    if account.client.user_id != user.pk:
        raise BankError("You can only access your own bank accounts.")


def _is_authorized_staff(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False

    role = getattr(user, "role", None)
    role_name = str(getattr(role, "name", "") or "").lower()

    return role_name == "staff"


# ==========================================
# SAVINGS CALCULATIONS
# ==========================================

def _add_months(start_date, months):
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])

    return date(year, month, day)


def _validate_term(term_months):
    try:
        term_months = int(term_months)
    except (TypeError, ValueError):
        raise BankError("Choose a valid savings term.")

    if term_months not in SUPPORTED_TERMS:
        raise BankError("Savings terms must be 3, 6, or 12 months.")

    return term_months


def _calculate_interest(amount, annual_rate, term_months):
    interest = (
        amount
        * annual_rate
        * Decimal(term_months)
        / Decimal("1200")
    )

    return interest.quantize(CENT, rounding=ROUND_HALF_UP)


def _deposit_remaining_principal(deposit):
    """
    Supports old deposits where remaining_principal may still be NULL.
    """

    if deposit.remaining_principal is None:
        if deposit.status == SavingsDeposit.Status.RELEASED:
            return ZERO

        return deposit.amount.quantize(CENT)

    return deposit.remaining_principal.quantize(CENT)

def _allocate_cash_withdrawal_to_deposits(savings, amount, by):
    """
    Reduce tracked deposit principal after an account-wide cash payout.

    Uses oldest deposits first so principal already paid in cash cannot
    later be released again through the deposit transfer workflow.
    """
    remaining = amount

    deposits = (
        SavingsDeposit.objects
        .select_for_update()
        .filter(
            savings_account=savings,
            status__in=[
                SavingsDeposit.Status.LOCKED,
                SavingsDeposit.Status.MATURED,
            ],
        )
        .order_by("deposited_at", "pk")
    )

    for deposit in deposits:
        if remaining <= ZERO:
            break

        principal = _deposit_remaining_principal(deposit)

        if principal <= ZERO:
            continue

        deducted = min(principal, remaining)
        new_principal = (principal - deducted).quantize(CENT)

        deposit.remaining_principal = new_principal

        fields = ["remaining_principal"]

        if new_principal <= ZERO:
            deposit.remaining_principal = ZERO
            deposit.interest_amount = ZERO
            deposit.status = SavingsDeposit.Status.RELEASED
            deposit.released_at = timezone.now()
            deposit.released_by = by

            fields.extend([
                "interest_amount",
                "status",
                "released_at",
                "released_by",
            ])
        elif _deposit_is_matured(deposit):
            old_interest = _calculate_remaining_interest(
                deposit,
                principal,
            )
            deposit.interest_amount = (
                old_interest * new_principal / principal
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            fields.append("interest_amount")

        deposit.save(update_fields=fields)
        remaining -= deducted

    return remaining

def _deposit_is_matured(deposit, today=None):
    today = today or timezone.localdate()

    return (
        deposit.status != SavingsDeposit.Status.RELEASED
        and deposit.maturity_date <= today
    )


def _get_matured_deposits(savings, today=None):
    today = today or timezone.localdate()

    return SavingsDeposit.objects.filter(
        savings_account=savings,
        status__in=[
            SavingsDeposit.Status.LOCKED,
            SavingsDeposit.Status.MATURED,
        ],
        maturity_date__lte=today,
    ).order_by("maturity_date", "deposited_at", "pk")


def _has_pending_request(model, deposit):
    return model.objects.filter(
        deposit=deposit,
        status="pending",
    ).exists()


def _require_no_other_pending_requests(deposit, exclude=None):
    """
    An approved cash withdrawal is also considered active because
    it is waiting for the client to receive the actual branch payout.

    This prevents another withdrawal or transfer from releasing
    the same deposit while an approved payout is still outstanding.
    """

    if exclude != SavingsEarlyWithdrawalRequest:
        if _has_pending_request(SavingsEarlyWithdrawalRequest, deposit):
            raise BankError(
                "This deposit already has a pending early withdrawal request."
            )

    if exclude != SavingsCashWithdrawalRequest:
        if SavingsCashWithdrawalRequest.objects.filter(
            deposit=deposit,
            status__in=["pending", "approved"],
        ).exists():
            raise BankError(
                "This deposit already has a pending or approved cash "
                "withdrawal request. Complete or reject that request first."
            )

    if exclude != SavingsTransferRequest:
        if _has_pending_request(SavingsTransferRequest, deposit):
            raise BankError(
                "This deposit already has a pending savings transfer request."
            )


def _validate_withdrawal_amount(amount, remaining_principal):
    try:
        amount = to_money(amount)
    except Exception:
        raise BankError("Enter a valid withdrawal amount.")

    if amount <= ZERO:
        raise BankError("Withdrawal amount must be greater than zero.")

    if amount > remaining_principal:
        raise BankError(
            "The requested amount exceeds the remaining principal "
            f"of PHP {remaining_principal:,.2f}."
        )

    return amount


def _calculate_remaining_interest(deposit, remaining_principal):
    """
    Returns the interest still available for payout.

    Before maturity, no interest is available.

    After maturity, interest is calculated against the remaining
    principal. Once a partial payout occurs, interest_amount stores
    the remaining interest so it cannot be paid twice.
    """

    if remaining_principal <= ZERO:
        return ZERO

    if not _deposit_is_matured(deposit):
        return ZERO

    if deposit.interest_amount and deposit.interest_amount > ZERO:
        return deposit.interest_amount.quantize(CENT)

    return _calculate_interest(
        remaining_principal,
        deposit.annual_rate,
        deposit.term_months,
    )


def _calculate_partial_interest(
    remaining_interest,
    withdrawal_amount,
    remaining_principal,
):
    """
    Allocates interest proportionally to the principal being withdrawn.

    The final withdrawal receives any remaining cents to prevent
    rounding from leaving unpaid interest behind.
    """

    if remaining_interest <= ZERO or remaining_principal <= ZERO:
        return ZERO

    if withdrawal_amount >= remaining_principal:
        return remaining_interest.quantize(CENT)

    interest = (
        remaining_interest
        * withdrawal_amount
        / remaining_principal
    )

    interest = interest.quantize(CENT, rounding=ROUND_HALF_UP)

    return min(interest, remaining_interest)


# ==========================================
# OPEN SAVINGS ACCOUNT
# ==========================================

@transaction.atomic
def open_account(client, by):
    client = type(client).objects.select_for_update().get(pk=client.pk)

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    if client.user_id != by.pk and not _is_authorized_staff(by):
        raise BankError("You cannot open an account for another client.")

    _require_no_security_freeze(client.pk)

    if SavingsAccount.objects.filter(client=client).exists():
        raise BankError("You already have a savings account.")

    for _ in range(10):
        number = f"{secrets.randbelow(10**10):010d}"

        if not SavingsAccount.objects.filter(account_number=number).exists():
            break
    else:
        raise BankError("Could not generate an account number. Try again.")

    account = SavingsAccount.objects.create(
        client=client,
        account_number=number,
    )

    log(
        by,
        "open_account",
        account,
        client_id=client.pk,
    )

    _notify_savings_event(
        client=client,
        kind=NOTIFICATION_KINDS["SAVINGS_OPENED"],
        client_message=(
            f"Your savings account {account.account_number} has been opened."
        ),
        staff_message=(
            f"A savings account was opened for client {client}."
        ),
        exclude_user=by,
    )

    return account


# ==========================================
# STAFF PHYSICAL SAVINGS DEPOSIT
# ==========================================

@transaction.atomic
def staff_savings_cash_deposit(
    savings_account_id,
    amount,
    by,
    term_months=3,
):
    """
    Records physical cash received at the branch.

    Every branch deposit becomes its own locked SavingsDeposit.
    The client must select a 3, 6, or 12-month term.
    """

    if not _is_authorized_staff(by):
        raise BankError("Only authorized staff can record savings deposits.")

    amount = to_money(amount)
    term_months = _validate_term(term_months)

    if amount <= ZERO:
        raise BankError("Deposit amount must be greater than zero.")

    savings = _lock_savings_account(savings_account_id)

    _require_active(savings)
    _require_no_security_freeze(savings.client_id)

    today = timezone.localdate()
    maturity_date = _add_months(today, term_months)

    reference = f"SAVDEP-{secrets.token_hex(6).upper()}"

    new_balance = savings.balance + amount
    savings.balance = new_balance
    savings.save(update_fields=["balance"])

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.DEPOSIT,
        amount=amount,
        balance_after=new_balance,
        savings_account=savings,
        reference=reference,
        created_by=by,
    )

    deposit = SavingsDeposit.objects.create(
        savings_account=savings,
        amount=amount,
        remaining_principal=amount,
        annual_rate=DEFAULT_ANNUAL_INTEREST_RATE,
        term_months=term_months,
        maturity_date=maturity_date,
        source=SavingsDeposit.Source.BRANCH_CASH,
        deposit_ledger_entry=entry,
    )

    log(
        by,
        "staff_savings_cash_deposit",
        savings,
        deposit_id=deposit.pk,
        amount=amount,
        term_months=term_months,
        maturity_date=str(maturity_date),
        reference=reference,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["CASH_DEPOSIT"],
        client_message=(
            f"A physical cash deposit of PHP {amount:,.2f} "
            f"was recorded in your savings account. "
            f"Term: {term_months} months. "
            f"Maturity date: {maturity_date}."
        ),
        staff_message=(
            f"Staff recorded a branch savings deposit of "
            f"PHP {amount:,.2f} for client {savings.client}. "
            f"Term: {term_months} months."
        ),
        exclude_user=by,
    )

    return {
        "entry": entry,
        "deposit": deposit,
        "reference": reference,
        "maturity_date": maturity_date,
    }


# ==========================================
# CLIENT REQUEST FOR PHYSICAL CASH WITHDRAWAL
# ==========================================
@transaction.atomic
def request_savings_cash_withdrawal(
    savings_account_id,
    amount,
    reason,
    by,
):
    """
    Client requests a specific amount from their total savings balance.

    No balance is deducted until staff confirms the actual branch payout.
    """

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    reason = (reason or "").strip()

    if not reason:
        raise BankError("Please provide a reason for the withdrawal.")

    savings = _lock_savings_account(savings_account_id)

    _require_owner(savings, by)
    _require_active(savings)
    _require_no_security_freeze(savings.client_id)

    amount = _validate_withdrawal_amount(amount, savings.balance)

    if SavingsCashWithdrawalRequest.objects.filter(
        savings_account=savings,
        status__in=[
            SavingsCashWithdrawalRequest.Status.PENDING,
            SavingsCashWithdrawalRequest.Status.APPROVED,
        ],
    ).exists():
        raise BankError(
            "You already have a pending or approved cash withdrawal request."
        )

    withdrawal_request = SavingsCashWithdrawalRequest.objects.create(
        savings_account=savings,
        deposit=None,
        requested_by=by,
        amount=amount,
        reason=reason,
    )

    log(
        by,
        "savings_cash_withdrawal_requested",
        savings,
        request_id=withdrawal_request.pk,
        amount=amount,
        reason=reason,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["CASH_WITHDRAWAL_REQUESTED"],
        client_message=(
            f"Your request to withdraw PHP {amount:,.2f} "
            "from your savings account has been submitted. "
            "Please wait for staff review."
        ),
        staff_message=(
            f"Client {savings.client} requested a physical cash "
            f"withdrawal of PHP {amount:,.2f} from their savings account."
        ),
    )

    return withdrawal_request

# ==========================================
# STAFF REVIEW OF PHYSICAL CASH WITHDRAWAL
# ==========================================
@transaction.atomic
def review_savings_cash_withdrawal_request(
    request_id,
    approved,
    reviewed_by,
    staff_notes="",
    branch_reference="",
):
    if not _is_authorized_staff(reviewed_by):
        raise BankError(
            "Only authorized staff can review savings withdrawal requests."
        )

    try:
        initial_request = (
            SavingsCashWithdrawalRequest.objects
            .select_related("savings_account", "deposit")
            .get(pk=request_id)
        )
    except SavingsCashWithdrawalRequest.DoesNotExist:
        raise BankError("Savings withdrawal request not found.")

    savings_account_id = initial_request.savings_account_id

    if not savings_account_id and initial_request.deposit_id:
        savings_account_id = initial_request.deposit.savings_account_id

    if not savings_account_id:
        raise BankError("The withdrawal request has no savings account.")

    savings = _lock_savings_account(savings_account_id)

    withdrawal_request = (
        SavingsCashWithdrawalRequest.objects
        .select_for_update()
        .get(pk=request_id)
    )

    staff_notes = (staff_notes or "").strip()

    # REJECT: Only pending requests can be rejected.
    if not approved:
        if withdrawal_request.status != SavingsCashWithdrawalRequest.Status.PENDING:
            raise BankError(
                "Only pending withdrawal requests can be rejected."
            )

        withdrawal_request.status = SavingsCashWithdrawalRequest.Status.REJECTED
        withdrawal_request.reviewed_by = reviewed_by
        withdrawal_request.reviewed_at = timezone.now()
        withdrawal_request.staff_notes = staff_notes

        withdrawal_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "staff_notes",
            ]
        )

        log(
            reviewed_by,
            "savings_cash_withdrawal_rejected",
            savings,
            request_id=withdrawal_request.pk,
            amount=withdrawal_request.amount,
            staff_notes=staff_notes,
        )

        _notify_savings_event(
            client=savings.client,
            kind=NOTIFICATION_KINDS["CASH_WITHDRAWAL_REJECTED"],
            client_message="Your savings withdrawal request was rejected.",
            staff_message=(
                f"Savings withdrawal request #{withdrawal_request.pk} "
                f"for {savings.client} was rejected."
            ),
            exclude_user=reviewed_by,
        )

        return {
            "request": withdrawal_request,
            "amount": withdrawal_request.amount,
            "reference": "",
        }

    # APPROVE: Allow pending requests and previously approved legacy requests.
    allowed_statuses = (
        SavingsCashWithdrawalRequest.Status.PENDING,
        SavingsCashWithdrawalRequest.Status.APPROVED,
    )

    if withdrawal_request.status not in allowed_statuses:
        raise BankError(
            "This withdrawal request has already been completed or rejected."
        )

    # Prevent duplicate transfers.
    if (
        withdrawal_request.payout_ledger_entry_id
        or withdrawal_request.paid_at
        or withdrawal_request.paid_by_id
        or withdrawal_request.branch_reference
    ):
        raise BankError(
            "This request already contains payout information. "
            "Please inspect its transaction records before processing."
        )

    _require_active(savings)
    _require_no_security_freeze(savings.client_id)

    amount = _validate_withdrawal_amount(
        withdrawal_request.amount,
        savings.balance,
    )

    bank_account = (
        BankAccount.objects
        .select_for_update()
        .select_related("client", "client__user")
        .filter(
            client_id=savings.client_id,
            status=BankAccount.Status.ACTIVE,
        )
        .first()
    )

    if bank_account is None:
        raise BankError(
            "The client's active regular bank account was not found."
        )

    _require_active_bank_account(bank_account)

    if bank_account.client_id != savings.client_id:
        raise BankError(
            "The bank account does not belong to this client."
        )

    # Generate a unique transfer reference.
    reference = f"SAVTRANSFER-{secrets.token_hex(6).upper()}"

    # Record review details only for a newly pending request.
    # Preserve the original approval details for legacy approved requests.
    if withdrawal_request.status == SavingsCashWithdrawalRequest.Status.PENDING:
        withdrawal_request.reviewed_by = reviewed_by
        withdrawal_request.reviewed_at = timezone.now()
        withdrawal_request.staff_notes = staff_notes

    # Transfer funds atomically.
    savings.balance -= amount
    bank_account.balance += amount

    savings.save(update_fields=["balance"])
    bank_account.save(update_fields=["balance"])

    savings_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT,
        amount=amount,
        balance_after=savings.balance,
        savings_account=savings,
        reference=reference,
        created_by=reviewed_by,
    )

    bank_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN,
        amount=amount,
        balance_after=bank_account.balance,
        bank_account=bank_account,
        reference=reference,
        created_by=reviewed_by,
    )

    # Prevent the same deposit principal from being released again later.
    _allocate_cash_withdrawal_to_deposits(
        savings,
        amount,
        reviewed_by,
    )

    # Complete the withdrawal request.
    withdrawal_request.status = SavingsCashWithdrawalRequest.Status.COMPLETED
    withdrawal_request.paid_by = reviewed_by
    withdrawal_request.paid_at = timezone.now()
    withdrawal_request.branch_reference = reference
    withdrawal_request.payout_ledger_entry = savings_entry

    withdrawal_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "staff_notes",
            "paid_by",
            "paid_at",
            "branch_reference",
            "payout_ledger_entry",
        ]
    )

    log(
        reviewed_by,
        "savings_cash_withdrawal_transferred",
        savings,
        request_id=withdrawal_request.pk,
        amount=amount,
        bank_account_id=bank_account.pk,
        savings_ledger_id=savings_entry.pk,
        bank_ledger_id=bank_entry.pk,
        reference=reference,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["CASH_WITHDRAWAL"],
        client_message=(
            f"Your savings withdrawal of PHP {amount:,.2f} "
            "has been transferred successfully to your regular bank account."
        ),
        staff_message=(
            f"Savings withdrawal of PHP {amount:,.2f} for "
            f"{savings.client} was transferred to their regular bank account."
        ),
        exclude_user=reviewed_by,
    )

    return {
        "request": withdrawal_request,
        "savings_entry": savings_entry,
        "bank_entry": bank_entry,
        "amount": amount,
        "reference": reference,
    }


# ==========================================
# DISABLE DIRECT STAFF CASH WITHDRAWAL
# ==========================================

@transaction.atomic
def staff_savings_cash_withdrawal(deposit_id, by):
    raise BankError(
        "Direct savings cash withdrawals are disabled. "
        "Review the client's withdrawal request and confirm payout "
        "after the physical cash has been handed over."
    )


# ==========================================
# TRANSFER FROM BANK TO SAVINGS
# ==========================================
def confirm_savings_cash_withdrawal_payout(*args, **kwargs):
    raise BankError(
        "Cash payout is no longer used. "
        "Savings withdrawals are transferred to the regular bank account "
        "when staff approves the request."
    )
# ==========================================
# RELEASE REMAINING SAVINGS TO BANK ACCOUNT
# ==========================================

def _release_deposit_locked(deposit, bank_account, savings, by, early=False):
    _require_active(savings)
    _require_active_bank_account(bank_account)

    if bank_account.client_id != savings.client_id:
        raise BankError(
            "The bank and savings accounts do not belong to the same client."
        )

    _require_no_security_freeze(savings.client_id)

    if deposit.status == SavingsDeposit.Status.RELEASED:
        raise BankError("This savings deposit has already been released.")

    _require_no_other_pending_requests(
        deposit,
        exclude=(
            SavingsTransferRequest
            if not early
            else SavingsEarlyWithdrawalRequest
        ),
    )

    if SavingsCashWithdrawalRequest.objects.filter(
    savings_account=savings,
    status__in=[
        SavingsCashWithdrawalRequest.Status.PENDING,
        SavingsCashWithdrawalRequest.Status.APPROVED,
    ],
    ).exists():
     raise BankError(
        "A savings cash withdrawal request is awaiting review or payout. "
        "Complete or reject it before releasing a deposit."
    )

    today = timezone.localdate()

    if not early and today < deposit.maturity_date:
        raise BankError(
            f"This deposit matures on {deposit.maturity_date}. "
            "Early withdrawal requires branch approval."
        )

    principal = _deposit_remaining_principal(deposit)

    if principal <= ZERO:
        raise BankError("This deposit has no remaining principal.")

    if savings.balance < principal:
        raise BankError(
            "Savings balance is insufficient to release this deposit."
        )

    interest = ZERO

    if not early:
        interest = _calculate_remaining_interest(
            deposit,
            principal,
        )

    total_release = principal + interest
    reference = f"REL-{secrets.token_hex(6).upper()}"

    if interest > ZERO:
        savings.balance += interest

        LedgerEntry.objects.create(
            entry_type=LedgerEntry.EntryType.INTEREST_CREDIT,
            amount=interest,
            balance_after=savings.balance,
            savings_account=savings,
            reference=f"{reference}-INT",
            created_by=by,
        )

    savings.balance -= total_release
    bank_account.balance += total_release

    savings.save(update_fields=["balance"])
    bank_account.save(update_fields=["balance"])

    savings_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT,
        amount=total_release,
        balance_after=savings.balance,
        savings_account=savings,
        reference=reference,
        created_by=by,
    )

    bank_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN,
        amount=total_release,
        balance_after=bank_account.balance,
        bank_account=bank_account,
        reference=reference,
        created_by=by,
    )

    deposit.interest_amount = ZERO
    deposit.remaining_principal = ZERO
    deposit.status = SavingsDeposit.Status.RELEASED
    deposit.release_ledger_entry = savings_entry
    deposit.released_at = timezone.now()
    deposit.released_by = by

    deposit.save(
        update_fields=[
            "interest_amount",
            "remaining_principal",
            "status",
            "release_ledger_entry",
            "released_at",
            "released_by",
        ]
    )

    log(
        by,
        "savings_deposit_released",
        savings,
        deposit_id=deposit.pk,
        principal=principal,
        interest=interest,
        total_release=total_release,
        early_withdrawal=early,
        reference=reference,
    )

    release_description = (
        "early withdrawal" if early else "matured savings deposit"
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["SAVINGS_RELEASED"],
        client_message=(
            f"Your {release_description} has been released. "
            f"PHP {total_release:,.2f} was transferred to your bank account. "
            f"Interest earned: PHP {interest:,.2f}."
        ),
        staff_message=(
            f"A {release_description} for client {savings.client} "
            f"was released. Total: PHP {total_release:,.2f}; "
            f"interest: PHP {interest:,.2f}."
        ),
        exclude_user=by,
    )

    return {
        "deposit": deposit,
        "principal": principal,
        "interest": interest,
        "total_release": total_release,
        "savings_entry": savings_entry,
        "bank_entry": bank_entry,
        "reference": reference,
    }


# ==========================================
# CLIENT REQUEST TO TRANSFER MATURED SAVINGS
# ==========================================

@transaction.atomic
def request_savings_transfer(deposit_id, by):
    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    try:
        initial = (
            SavingsDeposit.objects
            .select_related("savings_account", "savings_account__client")
            .get(pk=deposit_id)
        )
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    if initial.savings_account.client.user_id != by.pk:
        raise BankError(
            "You can only request a transfer from your own savings."
        )

    savings = _lock_savings_account(initial.savings_account_id)

    try:
        deposit = SavingsDeposit.objects.select_for_update().get(
            pk=deposit_id,
            savings_account=savings,
        )
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    _require_active(savings)
    _require_no_security_freeze(savings.client_id)

    if deposit.status == SavingsDeposit.Status.RELEASED:
        raise BankError("This deposit has already been released.")

    if not _deposit_is_matured(deposit):
        raise BankError(
            f"This deposit matures on {deposit.maturity_date}. "
            "Only matured deposits can be transferred."
        )

    if _deposit_remaining_principal(deposit) <= ZERO:
        raise BankError("This deposit has no remaining principal.")

    _require_no_other_pending_requests(deposit)

    request = SavingsTransferRequest.objects.create(
        deposit=deposit,
        requested_by=by,
    )

    log(
        by,
        "savings_transfer_requested",
        savings,
        deposit_id=deposit.pk,
        request_id=request.pk,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["TRANSFER_REQUESTED"],
        client_message=(
            "Your request to transfer matured savings to your regular "
            "bank account has been submitted for staff approval."
        ),
        staff_message=(
            f"Client {savings.client} submitted a transfer request "
            f"for matured savings deposit #{deposit.pk}."
        ),
    )

    return request


# ==========================================
# STAFF REVIEW OF SAVINGS TRANSFER REQUEST
# ==========================================

@transaction.atomic
def review_savings_transfer_request(
    request_id,
    approved,
    reviewed_by,
    staff_notes="",
):
    if not _is_authorized_staff(reviewed_by):
        raise BankError(
            "Only authorized staff can review savings transfer requests."
        )

    try:
        initial_request = (
            SavingsTransferRequest.objects
            .select_related(
                "deposit",
                "deposit__savings_account",
                "deposit__savings_account__client",
            )
            .get(pk=request_id)
        )
    except SavingsTransferRequest.DoesNotExist:
        raise BankError("Savings transfer request not found.")

    savings = _lock_savings_account(
        initial_request.deposit.savings_account_id
    )

    try:
        transfer_request = (
            SavingsTransferRequest.objects
            .select_for_update()
            .select_related("deposit")
            .get(pk=request_id)
        )
    except SavingsTransferRequest.DoesNotExist:
        raise BankError("Savings transfer request not found.")

    if transfer_request.status != SavingsTransferRequest.Status.PENDING:
        raise BankError("This transfer request has already been reviewed.")

    deposit = (
        SavingsDeposit.objects
        .select_for_update()
        .get(
            pk=transfer_request.deposit_id,
            savings_account=savings,
        )
    )

    staff_notes = (staff_notes or "").strip()

    if approved:
        _require_active(savings)
        _require_no_security_freeze(savings.client_id)

        if deposit.status == SavingsDeposit.Status.RELEASED:
            raise BankError("This savings deposit has already been released.")

        if not _deposit_is_matured(deposit):
            raise BankError("This deposit has not yet matured.")

        _require_no_other_pending_requests(
            deposit,
            exclude=SavingsTransferRequest,
        )

        bank_account = (
            BankAccount.objects
            .select_for_update()
            .select_related("client", "client__user")
            .filter(
                client_id=savings.client_id,
                status=BankAccount.Status.ACTIVE,
            )
            .first()
        )

        if bank_account is None:
            raise BankError(
                "The client's regular bank account was not found."
            )

        result = _release_deposit_locked(
            deposit,
            bank_account,
            savings,
            reviewed_by,
            early=False,
        )

        transfer_request.status = SavingsTransferRequest.Status.APPROVED
        transfer_request.reviewed_by = reviewed_by
        transfer_request.reviewed_at = timezone.now()
        transfer_request.staff_notes = staff_notes

        transfer_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "staff_notes",
            ]
        )

        log(
            reviewed_by,
            "savings_transfer_approved",
            savings,
            request_id=transfer_request.pk,
            deposit_id=deposit.pk,
            staff_notes=staff_notes,
        )

        _notify_savings_event(
            client=savings.client,
            kind=NOTIFICATION_KINDS["TRANSFER_APPROVED"],
            client_message=(
                "Your savings transfer request was approved. "
                f"PHP {result['total_release']:,.2f} was transferred "
                "to your regular bank account."
            ),
            staff_message=(
                f"Savings transfer request #{transfer_request.pk} "
                f"for client {savings.client} was approved."
            ),
            exclude_user=reviewed_by,
        )

        return result

    transfer_request.status = SavingsTransferRequest.Status.REJECTED
    transfer_request.reviewed_by = reviewed_by
    transfer_request.reviewed_at = timezone.now()
    transfer_request.staff_notes = staff_notes

    transfer_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "staff_notes",
        ]
    )

    log(
        reviewed_by,
        "savings_transfer_rejected",
        savings,
        request_id=transfer_request.pk,
        deposit_id=deposit.pk,
        staff_notes=staff_notes,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["TRANSFER_REJECTED"],
        client_message=(
            "Your request to transfer matured savings to your regular "
            "bank account was rejected. Please contact the branch "
            "if you need more information."
        ),
        staff_message=(
            f"Savings transfer request #{transfer_request.pk} "
            f"for client {savings.client} was rejected."
        ),
        exclude_user=reviewed_by,
    )

    return transfer_request


# ==========================================
# NORMAL MATURITY RELEASE - LEGACY COMPATIBILITY
# ==========================================

@transaction.atomic
def release_matured_deposit(deposit_id, by):
    """
    Direct maturity release is retained only for compatibility.
    Clients must request a transfer and staff must approve it.
    """

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    try:
        initial = (
            SavingsDeposit.objects
            .select_related(
                "savings_account",
                "savings_account__client",
            )
            .get(pk=deposit_id)
        )
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    if initial.savings_account.client.user_id == by.pk:
        raise BankError(
            "Direct maturity release is no longer available. "
            "Submit a transfer request for staff approval."
        )

    if not _is_authorized_staff(by):
        raise BankError("You are not authorized to release this deposit.")

    savings = _lock_savings_account(initial.savings_account_id)

    deposit = SavingsDeposit.objects.select_for_update().get(
        pk=deposit_id,
        savings_account=savings,
    )

    _require_no_other_pending_requests(deposit)

    bank_account = (
        BankAccount.objects
        .select_for_update()
        .select_related("client", "client__user")
        .filter(
            client_id=savings.client_id,
            status=BankAccount.Status.ACTIVE,
        )
        .first()
    )

    if bank_account is None:
        raise BankError("The client's regular bank account was not found.")

    return _release_deposit_locked(
        deposit,
        bank_account,
        savings,
        by,
        early=False,
    )


# ==========================================
# REQUEST EARLY WITHDRAWAL
# ==========================================

@transaction.atomic
def request_early_withdrawal(deposit_id, reason, by):
    reason = (reason or "").strip()

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    if not reason:
        raise BankError("Please provide a reason for early withdrawal.")

    try:
        initial = (
            SavingsDeposit.objects
            .select_related(
                "savings_account",
                "savings_account__client",
            )
            .get(pk=deposit_id)
        )
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    if initial.savings_account.client.user_id != by.pk:
        raise BankError(
            "You can only request withdrawal from your own deposit."
        )

    savings = _lock_savings_account(initial.savings_account_id)

    deposit = (
        SavingsDeposit.objects
        .select_for_update()
        .filter(pk=deposit_id, savings_account=savings)
        .first()
    )

    if deposit is None:
        raise BankError("Savings deposit not found.")

    _require_active(savings)
    _require_no_security_freeze(savings.client_id)

    if deposit.status != SavingsDeposit.Status.LOCKED:
        raise BankError("This deposit is not available for early withdrawal.")

    if timezone.localdate() >= deposit.maturity_date:
        raise BankError(
            "This deposit has reached maturity. "
            "Use the normal savings transfer or cash withdrawal process."
        )

    if _deposit_remaining_principal(deposit) <= ZERO:
        raise BankError("This deposit has no remaining principal.")

    _require_no_other_pending_requests(deposit)

    withdrawal_request = SavingsEarlyWithdrawalRequest.objects.create(
        deposit=deposit,
        requested_by=by,
        reason=reason,
    )

    log(
        by,
        "savings_early_withdrawal_requested",
        savings,
        deposit_id=deposit.pk,
        request_id=withdrawal_request.pk,
        reason=reason,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["EARLY_WITHDRAWAL_REQUESTED"],
        client_message=(
            "Your early withdrawal request has been submitted "
            "and is waiting for staff review."
        ),
        staff_message=(
            f"Client {savings.client} requested an early withdrawal "
            f"for savings deposit #{deposit.pk}."
        ),
    )

    return withdrawal_request


# ==========================================
# STAFF REVIEW OF EARLY WITHDRAWAL
# ==========================================

@transaction.atomic
def review_early_withdrawal_request(
    request_id,
    approved,
    reviewed_by,
    staff_notes="",
    branch_reference="",
):
    if not _is_authorized_staff(reviewed_by):
        raise BankError(
            "Only authorized staff can review withdrawal requests."
        )

    try:
        initial_request = (
            SavingsEarlyWithdrawalRequest.objects
            .select_related(
                "deposit",
                "deposit__savings_account",
                "deposit__savings_account__client",
            )
            .get(pk=request_id)
        )
    except SavingsEarlyWithdrawalRequest.DoesNotExist:
        raise BankError("Withdrawal request not found.")

    savings = _lock_savings_account(
        initial_request.deposit.savings_account_id
    )

    withdrawal_request = (
        SavingsEarlyWithdrawalRequest.objects
        .select_for_update()
        .get(pk=request_id)
    )

    if withdrawal_request.status != SavingsEarlyWithdrawalRequest.Status.PENDING:
        raise BankError("This request has already been reviewed.")

    deposit = (
        SavingsDeposit.objects
        .select_for_update()
        .get(
            pk=withdrawal_request.deposit_id,
            savings_account=savings,
        )
    )

    staff_notes = (staff_notes or "").strip()
    branch_reference = (branch_reference or "").strip()

    if approved and not branch_reference:
        raise BankError("A branch reference is required for approval.")

    if approved:
        _require_active(savings)

        _require_no_other_pending_requests(
            deposit,
            exclude=SavingsEarlyWithdrawalRequest,
        )

        _require_no_security_freeze(savings.client_id)

        bank_account = (
            BankAccount.objects
            .select_for_update()
            .select_related("client", "client__user")
            .filter(
                client_id=savings.client_id,
                status=BankAccount.Status.ACTIVE,
            )
            .first()
        )

        if bank_account is None:
            raise BankError(
                "The client's regular bank account was not found."
            )

        result = _release_deposit_locked(
            deposit,
            bank_account,
            savings,
            reviewed_by,
            early=True,
        )

        withdrawal_request.status = (
            SavingsEarlyWithdrawalRequest.Status.APPROVED
        )
        withdrawal_request.reviewed_by = reviewed_by
        withdrawal_request.reviewed_at = timezone.now()
        withdrawal_request.staff_notes = staff_notes
        withdrawal_request.branch_reference = branch_reference

        withdrawal_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "staff_notes",
                "branch_reference",
            ]
        )

        log(
            reviewed_by,
            "savings_early_withdrawal_approved",
            savings,
            request_id=withdrawal_request.pk,
            branch_reference=branch_reference,
        )

        _notify_savings_event(
            client=savings.client,
            kind=NOTIFICATION_KINDS["EARLY_WITHDRAWAL_APPROVED"],
            client_message=(
                "Your early withdrawal request was approved. "
                "The funds have been transferred to your regular bank account."
            ),
            staff_message=(
                f"Early withdrawal request #{withdrawal_request.pk} "
                f"for client {savings.client} was approved."
            ),
            exclude_user=reviewed_by,
        )

        return result

    withdrawal_request.status = (
        SavingsEarlyWithdrawalRequest.Status.REJECTED
    )
    withdrawal_request.reviewed_by = reviewed_by
    withdrawal_request.reviewed_at = timezone.now()
    withdrawal_request.staff_notes = staff_notes
    withdrawal_request.branch_reference = branch_reference

    withdrawal_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "staff_notes",
            "branch_reference",
        ]
    )

    log(
        reviewed_by,
        "savings_early_withdrawal_rejected",
        savings,
        request_id=withdrawal_request.pk,
        staff_notes=staff_notes,
    )

    _notify_savings_event(
        client=savings.client,
        kind=NOTIFICATION_KINDS["EARLY_WITHDRAWAL_REJECTED"],
        client_message=(
            "Your early withdrawal request was rejected. "
            "Please contact the bank if you need more information."
        ),
        staff_message=(
            f"Early withdrawal request #{withdrawal_request.pk} "
            f"for client {savings.client} was rejected."
        ),
        exclude_user=reviewed_by,
    )

    return withdrawal_request


# ==========================================
# DISABLED LEGACY OPERATIONS
# ==========================================

@transaction.atomic
def post_monthly_interest(*args, **kwargs):
    raise BankError(
        "Monthly account-wide interest posting is disabled. "
        "Interest is calculated per savings deposit upon release."
    )


@transaction.atomic
def deposit(*args, **kwargs):
    raise BankError(
        "Cash deposits must be processed at the branch. "
        "Use staff_savings_cash_deposit()."
    )


@transaction.atomic
def withdraw(*args, **kwargs):
    raise BankError(
        "Direct savings withdrawals are not allowed. "
        "Submit a withdrawal request for staff approval."
    )


# ==========================================
# LEGACY REGULAR BANK ACCOUNT CASH DEPOSIT
# ==========================================

@transaction.atomic
def staff_cash_deposit(bank_account_id, amount, by):
    """
    Records a physical deposit into a regular BankAccount.

    Savings branch deposits must use staff_savings_cash_deposit().
    """

    if not _is_authorized_staff(by):
        raise BankError("Only authorized staff can record cash deposits.")

    amount = to_money(amount)

    if amount <= ZERO:
        raise BankError("Deposit amount must be greater than zero.")

    account = _lock_bank_account(bank_account_id)

    _require_active_bank_account(account)
    _require_no_security_freeze(account.client_id)

    account.balance += amount
    account.save(update_fields=["balance"])

    reference = f"CASH-{secrets.token_hex(6).upper()}"

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.DEPOSIT,
        amount=amount,
        balance_after=account.balance,
        bank_account=account,
        reference=reference,
        created_by=by,
    )

    log(
        by,
        "staff_cash_deposit",
        account,
        amount=amount,
        reference=reference,
    )

    _notify_savings_event(
        client=account.client,
        kind=NOTIFICATION_KINDS["CASH_DEPOSIT"],
        client_message=(
            f"A cash deposit of PHP {amount:,.2f} was credited "
            f"to your bank account."
        ),
        staff_message=(
            f"A cash deposit of PHP {amount:,.2f} was recorded "
            f"for client {account.client}."
        ),
        exclude_user=by,
    )

    return entry