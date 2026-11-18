import secrets

from django.db import transaction

from accounting.models import LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log

from .models import SavingsAccount


def _lock(*account_ids):
    """Lock accounts in a fixed order so two transfers can never deadlock."""
    ids = sorted({int(i) for i in account_ids})
    accounts = {
        a.pk: a
        for a in SavingsAccount.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }
    if len(accounts) != len(ids):
        raise BankError("Account not found.")
    return accounts


def _require_active(account):
    if account.status != SavingsAccount.Status.ACTIVE:
        raise BankError(f"Account {account.account_number} is {account.status}.")


@transaction.atomic
def open_account(client, by):
    for _ in range(10):
        number = f"{secrets.randbelow(10**10):010d}"
        if not SavingsAccount.objects.filter(account_number=number).exists():
            break
    else:
        raise BankError("Could not generate an account number. Try again.")
    account = SavingsAccount.objects.create(client=client, account_number=number)
    log(by, "open_account", account, client_id=client.pk)
    return account


@transaction.atomic
def deposit(account_id, amount, by):
    amount = to_money(amount)
    account = _lock(account_id)[int(account_id)]
    _require_active(account)
    account.balance += amount
    account.save(update_fields=["balance"])
    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.DEPOSIT, amount=amount,
        balance_after=account.balance, savings_account=account, created_by=by,
    )
    log(by, "deposit", account, amount=amount)
    return entry


@transaction.atomic
def withdraw(account_id, amount, by):
    amount = to_money(amount)
    account = _lock(account_id)[int(account_id)]
    _require_active(account)
    if account.balance < amount:
        raise BankError("Insufficient funds.")
    account.balance -= amount
    account.save(update_fields=["balance"])
    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.WITHDRAWAL, amount=amount,
        balance_after=account.balance, savings_account=account, created_by=by,
    )
    log(by, "withdraw", account, amount=amount)
    return entry


@transaction.atomic
def transfer(from_account_id, to_account_number, amount, by):
    amount = to_money(amount)
    target = SavingsAccount.objects.filter(account_number=str(to_account_number).strip()).first()
    if target is None:
        raise BankError("Destination account not found.")
    if target.pk == int(from_account_id):
        raise BankError("You cannot transfer to the same account.")

    accounts = _lock(from_account_id, target.pk)
    source, dest = accounts[int(from_account_id)], accounts[target.pk]
    _require_active(source)
    _require_active(dest)
    if source.balance < amount:
        raise BankError("Insufficient funds.")

    source.balance -= amount
    dest.balance += amount
    source.save(update_fields=["balance"])
    dest.save(update_fields=["balance"])

    ref = f"TRF-{secrets.token_hex(4).upper()}"
    out = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT, amount=amount,
        balance_after=source.balance, savings_account=source, reference=ref, created_by=by,
    )
    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN, amount=amount,
        balance_after=dest.balance, savings_account=dest, reference=ref, created_by=by,
    )
    log(by, "transfer", source, amount=amount, to_account=dest.account_number, reference=ref)
    return out