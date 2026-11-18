from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounting.models import LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from savings.models import SavingsAccount

from .calculations import build_schedule
from .models import Installment, Loan

DECIDERS = ("admin", "loan_officer")   # may approve, reject and disburse
PAYMENT_TAKERS = ("admin", "staff")    # may record loan payments


def _require_role(user, allowed, message):
    if user.role.name not in allowed:
        raise BankError(message)


def _get_loan_locked(loan_id):
    try:
        return Loan.objects.select_for_update().get(pk=loan_id)
    except Loan.DoesNotExist:
        raise BankError("Loan not found.")


@transaction.atomic
def apply_for_loan(client, product, principal, term_months, by):
    principal = to_money(principal)
    try:
        term_months = int(term_months)
    except (TypeError, ValueError):
        raise BankError("Enter a valid number of months.")
    if not product.is_active:
        raise BankError("This loan product is not available.")
    if not (product.min_amount <= principal <= product.max_amount):
        raise BankError(f"Amount must be between {product.min_amount} and {product.max_amount}.")
    if not (product.min_months <= term_months <= product.max_months):
        raise BankError(f"Term must be between {product.min_months} and {product.max_months} months.")
    loan = Loan.objects.create(
        client=client, product=product, principal=principal,
        annual_rate=product.annual_rate, term_months=term_months,
    )
    log(by, "loan_apply", loan, principal=principal, term_months=term_months)
    return loan


@transaction.atomic
def approve_loan(loan_id, by):
    _require_role(by, DECIDERS, "You are not allowed to approve loans.")
    loan = _get_loan_locked(loan_id)
    if loan.status != Loan.Status.PENDING:
        raise BankError(f"Only pending loans can be approved (this one is {loan.status}).")
    if loan.client.user_id == by.pk:
        raise BankError("You cannot approve your own loan.")
    loan.status = Loan.Status.APPROVED
    loan.decided_by = by
    loan.decided_at = timezone.now()
    loan.save(update_fields=["status", "decided_by", "decided_at"])
    log(by, "loan_approve", loan)
    return loan

@transaction.atomic
def reject_loan(loan_id, by, reason):
    _require_role(by, DECIDERS, "You are not allowed to reject loans.")
    reason = (reason or "").strip()
    if not reason:
        raise BankError("A reason is required to reject a loan.")
    loan = _get_loan_locked(loan_id)
    if loan.status != Loan.Status.PENDING:
        raise BankError(f"Only pending loans can be rejected (this one is {loan.status}).")
    loan.status = Loan.Status.REJECTED
    loan.decided_by = by
    loan.decided_at = timezone.now()
    loan.reject_reason = reason[:255]
    loan.save(update_fields=["status", "decided_by", "decided_at", "reject_reason"])
    log(by, "loan_reject", loan, reason=reason)
    return loan


@transaction.atomic
def disburse_loan(loan_id, by, savings_account_id):
    _require_role(by, DECIDERS, "You are not allowed to disburse loans.")
    loan = _get_loan_locked(loan_id)
    if loan.status != Loan.Status.APPROVED:
        raise BankError(f"Only approved loans can be disbursed (this one is {loan.status}).")
    try:
        account = SavingsAccount.objects.select_for_update().get(pk=savings_account_id)
    except SavingsAccount.DoesNotExist:
        raise BankError("Savings account not found.")
    if account.client_id != loan.client_id:
        raise BankError("That account does not belong to the loan's client.")
    if account.status != SavingsAccount.Status.ACTIVE:
        raise BankError(f"Account {account.account_number} is {account.status}.")

    today = timezone.localdate()
    rows = build_schedule(loan.principal, loan.annual_rate, loan.term_months, today)
    Installment.objects.bulk_create([
        Installment(
            loan=loan, number=r["number"], due_date=r["due_date"],
            principal_due=r["principal_due"], interest_due=r["interest_due"],
        )
        for r in rows
    ])

    account.balance += loan.principal
    account.save(update_fields=["balance"])
    LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.LOAN_DISBURSEMENT, amount=loan.principal,
        balance_after=account.balance, savings_account=account, loan=loan, created_by=by,
    )

    loan.status = Loan.Status.ACTIVE
    loan.disbursed_at = timezone.now()
    loan.start_date = today
    loan.save(update_fields=["status", "disbursed_at", "start_date"])
    log(by, "loan_disburse", loan, account=account.account_number, amount=loan.principal)
    return loan


@transaction.atomic
def record_payment(loan_id, amount, by):
    _require_role(by, PAYMENT_TAKERS, "You are not allowed to record loan payments.")
    amount = to_money(amount)
    loan = _get_loan_locked(loan_id)
    if loan.status != Loan.Status.ACTIVE:
        raise BankError(f"Payments can only be recorded on active loans (this one is {loan.status}).")

    unpaid = list(
        loan.installments.select_for_update().exclude(status=Installment.Status.PAID).order_by("number")
    )
    remaining = sum((i.total_due - i.amount_paid for i in unpaid), start=Decimal("0.00"))
    if amount > remaining:
        raise BankError(f"Payment is more than the remaining balance ({remaining}).")

    now = timezone.now()
    left = amount
    for inst in unpaid:
        pay = min(inst.total_due - inst.amount_paid, left)
        inst.amount_paid += pay
        if inst.amount_paid >= inst.total_due:
            inst.status = Installment.Status.PAID
            inst.paid_at = now
        inst.save(update_fields=["amount_paid", "status", "paid_at"])
        left -= pay
        if left == 0:
            break

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.LOAN_PAYMENT, amount=amount, loan=loan, created_by=by,
    )
    if amount == remaining:
        loan.status = Loan.Status.PAID
        loan.save(update_fields=["status"])
    log(by, "loan_payment", loan, amount=amount)
    return entry