
from uuid import uuid4

from django.db import transaction

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from notifications.models import Notification


@transaction.atomic
def client_bank_transfer(
    source_account_id,
    destination_account_number,
    amount,
    by,
):
    if not by.is_authenticated:
        raise BankError("Please log in first.")

    role = getattr(getattr(by, "role", None), "name", None)

    if role != "client":
        raise BankError("Only clients can use this transfer service.")

    amount = to_money(amount)

    try:
        source_id = int(source_account_id)
    except (ValueError, TypeError):
        raise BankError("Invalid source account.")

    destination_number = str(
        destination_account_number or ""
    ).strip()

    if not destination_number:
        raise BankError("Enter a destination account number.")

    # Find the destination before locking both accounts.
    try:
        destination_id = BankAccount.objects.only("pk").get(
            account_number=destination_number
        ).pk
    except BankAccount.DoesNotExist:
        raise BankError("Destination bank account not found.")

    if source_id == destination_id:
        raise BankError("You cannot transfer to the same account.")

    # Lock accounts in a consistent order.
    accounts = list(
        BankAccount.objects
        .select_related("client__user")
        .select_for_update()
        .filter(pk__in=[source_id, destination_id])
        .order_by("pk")
    )

    if len(accounts) != 2:
        raise BankError("One or both bank accounts were not found.")

    account_map = {
        account.pk: account
        for account in accounts
    }

    source = account_map[source_id]
    destination = account_map[destination_id]

    # Critical security check: source must belong to user.
    if source.client.user_id != by.pk:
        raise BankError(
            "You are not authorized to transfer from this account."
        )

    if source.status != BankAccount.Status.ACTIVE:
        raise BankError("Your source account is not active.")

    if destination.status != BankAccount.Status.ACTIVE:
        raise BankError("Destination account is not active.")

    if source.balance < amount:
        raise BankError("Insufficient bank account balance.")

    source.balance -= amount
    destination.balance += amount

    source.save(update_fields=["balance"])
    destination.save(update_fields=["balance"])

    reference = f"TRF-{uuid4().hex[:16].upper()}"

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
        "client_bank_transfer",
        source,
        destination=destination.account_number,
        amount=str(amount),
        reference=reference,
    )

    Notification.objects.create(
        user=source.client.user,
        kind="bank_transfer_out",
        message=(
            f"PHP {amount:,.2f} was transferred from "
            f"{source.account_number} to "
            f"{destination.account_number}. "
            f"Reference: {reference}"
        ),
    )

    Notification.objects.create(
        user=destination.client.user,
        kind="bank_transfer_in",
        message=(
            f"PHP {amount:,.2f} was received in "
            f"{destination.account_number}. "
            f"Reference: {reference}"
        ),
    )

    return outgoing, incoming
