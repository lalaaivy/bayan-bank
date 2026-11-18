from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")


class BankError(Exception):
    """A business rule was broken. The message is safe to show to the user."""


def to_money(value):
    """Turn user input into a valid positive Decimal with at most 2 decimals."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise BankError("Enter a valid amount.")
    if not amount.is_finite():
        raise BankError("Enter a valid amount.")
    if amount <= 0:
        raise BankError("Amount must be greater than zero.")
    if amount > MAX_AMOUNT:
        raise BankError("Amount is too large.")
    if amount != amount.quantize(CENT):
        raise BankError("Amount can have at most 2 decimal places.")
    return amount.quantize(CENT)