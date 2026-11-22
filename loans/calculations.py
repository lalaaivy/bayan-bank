
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ONE_HUNDRED = Decimal("100")
MONTHS_PER_YEAR = Decimal("12")


def _to_decimal(value, field_name):
    """Safely convert a value into a finite Decimal."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}.")

    if not result.is_finite():
        raise ValueError(f"Invalid {field_name}.")

    return result


def _validate_inputs(principal, annual_rate, months):
    principal = _to_decimal(principal, "principal")
    annual_rate = _to_decimal(annual_rate, "annual interest rate")

    try:
        months_decimal = Decimal(str(months))
        months_int = int(months_decimal)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        raise ValueError("Loan term must be a valid whole number of months.")

    if months_decimal != Decimal(months_int):
        raise ValueError("Loan term must be a whole number of months.")

    if principal <= ZERO:
        raise ValueError("Loan principal must be greater than zero.")

    if annual_rate < ZERO:
        raise ValueError("Annual interest rate cannot be negative.")

    if months_int <= 0:
        raise ValueError("Loan term must be at least one month.")

    return principal, annual_rate, months_int


def monthly_installment(principal, annual_rate, months):
    """
    Calculate the regular monthly installment using the
    fixed-payment amortization formula.

    Formula:
        M = P * r / (1 - (1 + r) ** -n)

    Where:
        M = monthly installment
        P = principal
        r = monthly interest rate
        n = number of monthly installments
    """
    principal, annual_rate, months = _validate_inputs(
        principal,
        annual_rate,
        months,
    )

    monthly_rate = (
        annual_rate / ONE_HUNDRED / MONTHS_PER_YEAR
    )

    if monthly_rate == ZERO:
        return (
            principal / Decimal(months)
        ).quantize(CENT, rounding=ROUND_HALF_UP)

    installment = (
        principal
        * monthly_rate
        / (
            Decimal("1")
            - (Decimal("1") + monthly_rate) ** (-months)
        )
    )

    return installment.quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def build_schedule(principal, annual_rate, months, start_date):
    """
    Generate a monthly amortization schedule.

    Interest is calculated using the outstanding principal.
    The final installment pays the remaining principal in full,
    accounting for rounding differences.

    start_date is normally the loan disbursement date.
    """
    principal, annual_rate, months = _validate_inputs(
        principal,
        annual_rate,
        months,
    )

    if start_date is None:
        raise ValueError("A loan schedule start date is required.")

    monthly_rate = (
        annual_rate / ONE_HUNDRED / MONTHS_PER_YEAR
    )

    installment = monthly_installment(
        principal,
        annual_rate,
        months,
    )

    balance = principal
    rows = []

    for number in range(1, months + 1):
        interest = (
            balance * monthly_rate
        ).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        if number == months:
            # Clear the remaining principal in the final installment.
            principal_part = balance
        else:
            principal_part = installment - interest

            if principal_part <= ZERO:
                raise ValueError(
                    "The monthly installment is insufficient to reduce "
                    "the outstanding principal."
                )

            if principal_part > balance:
                principal_part = balance

        principal_part = principal_part.quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        balance = (
            balance - principal_part
        ).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )

        if balance < ZERO:
            raise ValueError(
                "Invalid amortization calculation: negative balance."
            )

        rows.append({
            "number": number,
            "due_date": start_date + relativedelta(months=number),
            "principal_due": principal_part,
            "interest_due": interest,
            "balance": balance,
        })

    return rows
