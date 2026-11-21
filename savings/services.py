
import calendar
import secrets
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log

from .models import (
    SavingsAccount,
    SavingsDeposit,
    SavingsEarlyWithdrawalRequest,
)


CENT = Decimal("0.01")
DEFAULT_ANNUAL_INTEREST_RATE = Decimal("2.00")
SUPPORTED_TERMS = (3, 6, 12)


def _lock_savings_account(account_id):
    try:
        return SavingsAccount.objects.select_for_update().get(
            pk=int(account_id)
        )
    except (SavingsAccount.DoesNotExist, TypeError, ValueError):
        raise BankError("Savings account not found.")


def _lock_bank_account(account_id):
    try:
        return BankAccount.objects.select_for_update().get(
            pk=int(account_id)
        )
    except (BankAccount.DoesNotExist, TypeError, ValueError):
        raise BankError("Bank account not found.")


def _require_active(account):
    if account.status != SavingsAccount.Status.ACTIVE:
        raise BankError(
            f"Savings account {account.account_number} is {account.status}."
        )


def _require_active_bank_account(account):
    if account.status != "active":
        raise BankError(
            f"Bank account {account.account_number} is {account.status}."
        )


def _require_owner(account, user):
    if not user or not user.is_authenticated:
        raise BankError("Authentication is required.")

    if account.client.user_id != user.pk:
        raise BankError("You can only access your own bank accounts.")


def _add_months(start_date, months):
    """Add calendar months while keeping the day valid."""
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


def _is_authorized_staff(user):
    if not user or not user.is_authenticated:
        return False

    if getattr(user, "is_superuser", False):
        return True

    role = getattr(user, "role", None)
    role_name = getattr(role, "name", "").lower()

    return role_name in ("admin", "staff")


@transaction.atomic
def open_account(client, by):
    client = type(client).objects.select_for_update().get(pk=client.pk)

    if SavingsAccount.objects.filter(client=client).exists():
        raise BankError("You already have a savings account.")

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    if client.user_id != by.pk and not _is_authorized_staff(by):
        raise BankError("You cannot open an account for another client.")

    for _ in range(10):
        number = f"{secrets.randbelow(10**10):010d}"

        if not SavingsAccount.objects.filter(
            account_number=number
        ).exists():
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

    return account


@transaction.atomic
def staff_cash_deposit(bank_account_id, amount, by):
    if not _is_authorized_staff(by):
        raise BankError("Only authorized staff can record cash deposits.")

    amount = to_money(amount)

    if amount <= Decimal("0.00"):
        raise BankError("Deposit amount must be greater than zero.")

    account = _lock_bank_account(bank_account_id)
    _require_active_bank_account(account)

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

    return entry


@transaction.atomic
def transfer_to_savings(
    bank_account_id,
    savings_account_id,
    amount,
    by,
    term_months=3,
):
    amount = to_money(amount)
    term_months = _validate_term(term_months)

    bank_account = _lock_bank_account(bank_account_id)
    savings = _lock_savings_account(savings_account_id)

    _require_active_bank_account(bank_account)
    _require_active(savings)

    if bank_account.client_id != savings.client_id:
        raise BankError(
            "You can only transfer money into your own savings account."
        )

    _require_owner(bank_account, by)
    _require_owner(savings, by)

    if amount <= Decimal("0.00"):
        raise BankError("Transfer amount must be greater than zero.")

    if bank_account.balance < amount:
        raise BankError("Insufficient funds in your bank account.")

    today = timezone.localdate()
    maturity_date = _add_months(today, term_months)

    bank_account.balance -= amount
    savings.balance += amount

    bank_account.save(update_fields=["balance"])
    savings.save(update_fields=["balance"])

    reference = f"TRF-{secrets.token_hex(6).upper()}"

    bank_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT,
        amount=amount,
        balance_after=bank_account.balance,
        bank_account=bank_account,
        reference=reference,
        created_by=by,
    )

    savings_entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN,
        amount=amount,
        balance_after=savings.balance,
        savings_account=savings,
        reference=reference,
        created_by=by,
    )

    deposit = SavingsDeposit.objects.create(
        savings_account=savings,
        amount=amount,
        annual_rate=DEFAULT_ANNUAL_INTEREST_RATE,
        term_months=term_months,
        maturity_date=maturity_date,
        deposit_ledger_entry=savings_entry,
    )

    log(
        by,
        "bank_to_savings_transfer",
        savings,
        amount=amount,
        term_months=term_months,
        maturity_date=str(maturity_date),
        from_account=bank_account.account_number,
        to_account=savings.account_number,
        reference=reference,
        deposit_id=deposit.pk,
    )

    return {
        "bank_entry": bank_entry,
        "savings_entry": savings_entry,
        "deposit": deposit,
        "reference": reference,
    }


def _release_deposit_locked(deposit, bank_account, savings, by, early=False):
    _require_active(savings)
    _require_active_bank_account(bank_account)

    if bank_account.client_id != savings.client_id:
        raise BankError("The bank and savings accounts do not belong to the same client.")

    if deposit.status == SavingsDeposit.Status.RELEASED:
        raise BankError("This savings deposit has already been released.")

    today = timezone.localdate()

    if not early and today < deposit.maturity_date:
        raise BankError(
            f"This deposit matures on {deposit.maturity_date}. "
            "Early withdrawal requires branch approval."
        )

    if savings.balance < deposit.amount:
        raise BankError("Savings balance is insufficient to release this deposit.")

    interest = Decimal("0.00")

    if not early:
        interest = _calculate_interest(
            deposit.amount,
            deposit.annual_rate,
            deposit.term_months,
        )

    total_release = deposit.amount + interest
    reference = f"REL-{secrets.token_hex(6).upper()}"

    if interest > 0:
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

    deposit.interest_amount = interest
    deposit.status = SavingsDeposit.Status.RELEASED
    deposit.release_ledger_entry = savings_entry
    deposit.released_at = timezone.now()
    deposit.released_by = by

    deposit.save(
        update_fields=[
            "interest_amount",
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
        principal=deposit.amount,
        interest=interest,
        total_release=total_release,
        early_withdrawal=early,
        reference=reference,
    )

    return {
        "deposit": deposit,
        "principal": deposit.amount,
        "interest": interest,
        "total_release": total_release,
        "savings_entry": savings_entry,
        "bank_entry": bank_entry,
        "reference": reference,
    }


@transaction.atomic
def release_matured_deposit(deposit_id, by):
    try:
        initial = SavingsDeposit.objects.select_related(
            "savings_account"
        ).get(pk=deposit_id)
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    savings_id = initial.savings_account_id
    client_id = initial.savings_account.client_id

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    if initial.savings_account.client.user_id != by.pk and not _is_authorized_staff(by):
        raise BankError("You are not authorized to release this deposit.")

    bank_account = (
        BankAccount.objects.select_for_update()
        .filter(client_id=client_id)
        .first()
    )

    if bank_account is None:
        raise BankError("The client's regular bank account was not found.")

    savings = _lock_savings_account(savings_id)

    try:
        deposit = SavingsDeposit.objects.select_for_update().get(
            pk=deposit_id,
            savings_account=savings,
        )
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    return _release_deposit_locked(
        deposit,
        bank_account,
        savings,
        by,
        early=False,
    )


@transaction.atomic
def request_early_withdrawal(deposit_id, reason, by):
    reason = (reason or "").strip()

    if not by or not by.is_authenticated:
        raise BankError("Authentication is required.")

    if not reason:
        raise BankError("Please provide a reason for early withdrawal.")

    try:
        deposit = SavingsDeposit.objects.select_for_update().select_related(
            "savings_account",
            "savings_account__client",
        ).get(pk=deposit_id)
    except SavingsDeposit.DoesNotExist:
        raise BankError("Savings deposit not found.")

    if deposit.savings_account.client.user_id != by.pk:
        raise BankError("You can only request withdrawal from your own deposit.")

    if deposit.status != SavingsDeposit.Status.LOCKED:
        raise BankError("This deposit is not available for early withdrawal.")

    if timezone.localdate() >= deposit.maturity_date:
        raise BankError(
            "This deposit has reached maturity. Use the normal release process."
        )

    pending = SavingsEarlyWithdrawalRequest.objects.filter(
        deposit=deposit,
        status=SavingsEarlyWithdrawalRequest.Status.PENDING,
    ).exists()

    if pending:
        raise BankError("There is already a pending early withdrawal request.")

    withdrawal_request = SavingsEarlyWithdrawalRequest.objects.create(
        deposit=deposit,
        requested_by=by,
        reason=reason,
    )

    log(
        by,
        "savings_early_withdrawal_requested",
        deposit.savings_account,
        deposit_id=deposit.pk,
        request_id=withdrawal_request.pk,
        reason=reason,
    )

    return withdrawal_request


@transaction.atomic
def review_early_withdrawal_request(
    request_id,
    approved,
    reviewed_by,
    staff_notes="",
    branch_reference="",
):
    if not _is_authorized_staff(reviewed_by):
        raise BankError("Only authorized staff can review withdrawal requests.")

    try:
        withdrawal_request = (
            SavingsEarlyWithdrawalRequest.objects.select_for_update()
            .select_related(
                "deposit",
                "deposit__savings_account",
                "deposit__savings_account__client",
            )
            .get(pk=request_id)
        )
    except SavingsEarlyWithdrawalRequest.DoesNotExist:
        raise BankError("Withdrawal request not found.")

    if withdrawal_request.status != SavingsEarlyWithdrawalRequest.Status.PENDING:
        raise BankError("This request has already been reviewed.")

    staff_notes = (staff_notes or "").strip()
    branch_reference = (branch_reference or "").strip()

    if approved and not branch_reference:
        raise BankError("A branch reference is required for approval.")

    withdrawal_request.reviewed_by = reviewed_by
    withdrawal_request.reviewed_at = timezone.now()
    withdrawal_request.staff_notes = staff_notes
    withdrawal_request.branch_reference = branch_reference

    if approved:
        initial_deposit = withdrawal_request.deposit
        savings_id = initial_deposit.savings_account_id
        client_id = initial_deposit.savings_account.client_id

        bank_account = (
            BankAccount.objects.select_for_update()
            .filter(client_id=client_id)
            .first()
        )

        if bank_account is None:
            raise BankError("The client's regular bank account was not found.")

        savings = _lock_savings_account(savings_id)

        deposit = SavingsDeposit.objects.select_for_update().get(
            pk=initial_deposit.pk,
            savings_account=savings,
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

        return result

    withdrawal_request.status = (
        SavingsEarlyWithdrawalRequest.Status.REJECTED
    )

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
        withdrawal_request.deposit.savings_account,
        request_id=withdrawal_request.pk,
        staff_notes=staff_notes,
    )

    return withdrawal_request


@transaction.atomic
def post_monthly_interest(*args, **kwargs):
    raise BankError(
        "Monthly account-wide interest posting is disabled. "
        "Interest is calculated per savings deposit upon release."
    )


@transaction.atomic
def deposit(*args, **kwargs):
    raise BankError(
        "Cash deposits must first be credited to the client's regular "
        "bank account. Use staff_cash_deposit()."
    )


@transaction.atomic
def withdraw(*args, **kwargs):
    raise BankError(
        "Direct savings withdrawals are not allowed. "
        "Use the maturity release or approved early withdrawal process."
    )
