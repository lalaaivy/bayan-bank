from django.db import transaction

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from clients.services import client_has_active_security_freeze
from notifications.models import Notification


TRANSACTION_ROLES = ("staff",)


def _require_staff(user):
    role = getattr(getattr(user, "role", None), "name", None)

    if role not in TRANSACTION_ROLES:
        raise BankError(
            "Only authorized bank staff can process transactions."
        )


def _get_active_account(account_id):
    try:
        account = (
            BankAccount.objects
            .select_for_update()
            .select_related("client", "client__user")
            .get(pk=account_id)
        )
    except (BankAccount.DoesNotExist, ValueError, TypeError):
        raise BankError("Bank account not found.")

    if account.status != BankAccount.Status.ACTIVE:
        raise BankError(
            f"Bank account {account.account_number} is not active."
        )

    if client_has_active_security_freeze(account.client_id):
        raise BankError(
            "This client's account is under a security restriction. "
            "Transactions are currently unavailable."
        )

    return account


# ==========================================
# DEPOSIT
# ==========================================

@transaction.atomic
def deposit_to_bank(account_id, amount, by):
    _require_staff(by)
    amount = to_money(amount)

    account = _get_active_account(account_id)

    account.balance += amount
    account.save(update_fields=["balance"])

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.DEPOSIT,
        amount=amount,
        balance_after=account.balance,
        bank_account=account,
        created_by=by,
    )

    log(
        by,
        "bank_deposit",
        account,
        amount=str(amount),
    )

    Notification.objects.create(
        user=account.client.user,
        kind="bank_deposit",
        message=(
            f"PHP {amount:,.2f} was deposited into "
            f"{account.account_number}."
        ),
    )

    return entry


# ==========================================
# WITHDRAWAL
# ==========================================

@transaction.atomic
def withdraw_from_bank(account_id, amount, by):
    _require_staff(by)
    amount = to_money(amount)

    account = _get_active_account(account_id)

    if account.balance < amount:
        raise BankError("Insufficient bank account balance.")

    account.balance -= amount
    account.save(update_fields=["balance"])

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.WITHDRAWAL,
        amount=amount,
        balance_after=account.balance,
        bank_account=account,
        created_by=by,
    )

    log(
        by,
        "bank_withdrawal",
        account,
        amount=str(amount),
    )

    Notification.objects.create(
        user=account.client.user,
        kind="bank_withdrawal",
        message=(
            f"PHP {amount:,.2f} was withdrawn from "
            f"{account.account_number}."
        ),
    )

    return entry


# ==========================================
# BANK-TO-BANK TRANSFER
# ==========================================

@transaction.atomic
def transfer_between_banks(
    source_account_id,
    destination_account_id,
    amount,
    by,
):
    _require_staff(by)
    amount = to_money(amount)

    try:
        source_id = int(source_account_id)
        destination_id = int(destination_account_id)
    except (TypeError, ValueError):
        raise BankError("Invalid bank account selection.")

    if source_id == destination_id:
        raise BankError(
            "Source and destination accounts must be different."
        )

    # Lock both accounts in a consistent order.
    accounts = list(
        BankAccount.objects
        .select_for_update()
        .select_related("client", "client__user")
        .filter(pk__in=[source_id, destination_id])
        .order_by("pk")
    )

    if len(accounts) != 2:
        raise BankError("One or both bank accounts were not found.")

    account_map = {account.pk: account for account in accounts}

    source = account_map[source_id]
    destination = account_map[destination_id]

    if source.status != BankAccount.Status.ACTIVE:
        raise BankError("Source bank account is not active.")

    if destination.status != BankAccount.Status.ACTIVE:
        raise BankError("Destination bank account is not active.")

    # Check both clients. This blocks outgoing transfers from
    # frozen clients and incoming transfers to frozen clients.
    if client_has_active_security_freeze(source.client_id):
        raise BankError(
            "The sender's account is under a security restriction. "
            "The transfer cannot be processed."
        )

    if client_has_active_security_freeze(destination.client_id):
        raise BankError(
            "The recipient's account is under a security restriction. "
            "The transfer cannot be received."
        )

    if source.balance < amount:
        raise BankError("Insufficient bank account balance.")

    source.balance -= amount
    destination.balance += amount

    source.save(update_fields=["balance"])
    destination.save(update_fields=["balance"])

    reference = f"TRANSFER-{source.pk}-{destination.pk}"

    outgoing = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT,
        amount=amount,
        balance_after=source.balance,
        bank_account=source,
        reference=reference,
        created_by=by,
    )

    incoming = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN,
        amount=amount,
        balance_after=destination.balance,
        bank_account=destination,
        reference=reference,
        created_by=by,
    )

    log(
        by,
        "bank_transfer",
        source,
        destination=destination.account_number,
        amount=str(amount),
    )

    Notification.objects.create(
        user=source.client.user,
        kind="bank_transfer_out",
        message=(
            f"PHP {amount:,.2f} was transferred from "
            f"{source.account_number} to "
            f"{destination.account_number}."
        ),
    )

    Notification.objects.create(
        user=destination.client.user,
        kind="bank_transfer_in",
        message=(
            f"PHP {amount:,.2f} was received in "
            f"{destination.account_number}."
        ),
    )

    return outgoing, incoming