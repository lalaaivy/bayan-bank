
from uuid import uuid4

from django.db import transaction

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from notifications.models import Notification
from savings.models import SavingsAccount


@transaction.atomic
def transfer_bank_to_savings(
    bank_account_id,
    savings_account_id,
    amount,
    by,
):
    if (
        not by.is_authenticated
        or getattr(getattr(by, "role", None), "name", None) != "client"
    ):
        raise BankError(
            "Only clients can transfer money into their savings."
        )

    amount = to_money(amount)

    bank = (
        BankAccount.objects
        .select_for_update()
        .select_related("client")
        .get(pk=bank_account_id)
    )

    savings = (
        SavingsAccount.objects
        .select_for_update()
        .select_related("client")
        .get(pk=savings_account_id)
    )

    if bank.client.user_id != by.pk or savings.client.user_id != by.pk:
        raise BankError(
            "You can only transfer between your own accounts."
        )

    if bank.status != BankAccount.Status.ACTIVE:
        raise BankError("Regular bank account is not active.")

    if savings.status != SavingsAccount.Status.ACTIVE:
        raise BankError("Savings account is not active.")

    if bank.balance < amount:
        raise BankError("Insufficient regular bank account balance.")

    bank.balance -= amount
    savings.balance += amount

    bank.save(update_fields=["balance"])
    savings.save(update_fields=["balance"])

    reference = f"BTS-{uuid4().hex[:16].upper()}"

    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_OUT,
        amount=amount,
        balance_after=bank.balance,
        bank_account=bank,
        reference=reference,
        created_by=by,
    )

    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.TRANSFER_IN,
        amount=amount,
        balance_after=savings.balance,
        savings_account=savings,
        reference=reference,
        created_by=by,
    )

    log(
        by,
        "bank_to_savings_transfer",
        savings,
        amount=amount,
        reference=reference,
    )

    Notification.objects.create(
        user=by,
        kind="savings_transfer",
        message=(
            f"PHP {amount:,.2f} transferred from "
            "your regular bank account to savings."
        ),
    )

    return reference
