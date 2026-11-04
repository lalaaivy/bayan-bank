from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

CENT = Decimal("0.01")

def monthly_installment(principal, annual_rate, months):
    principal = Decimal(principal)
    r = Decimal(annual_rate) / 100 / 12
    if r == 0:
        return (principal / months).quantize(CENT, ROUND_HALF_UP)
    m = principal * r / (1 - (1 + r) ** -months)
    return m.quantize(CENT, ROUND_HALF_UP)

def build_schedule(principal, annual_rate, months, start_date):
    principal = Decimal(principal)
    r = Decimal(annual_rate) / 100 / 12
    installment = monthly_installment(principal, annual_rate, months)
    balance = principal
    rows = []
    for n in range(1, months + 1):
        interest = (balance * r).quantize(CENT, ROUND_HALF_UP)
        principal_part = balance if n == months else installment - interest
        balance -= principal_part
        rows.append({
            "number": n,
            "due_date": start_date + relativedelta(months=n),
            "principal_due": principal_part,
            "interest_due": interest,
            "balance": balance,
        })
    return rows