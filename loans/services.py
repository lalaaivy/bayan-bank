
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from notifications.models import Notification
from savings.models import SavingsAccount

from .calculations import build_schedule, monthly_installment
from .models import (
    Disbursement,
    EligibilityCheck,
    Installment,
    Loan,
    LoanAgreement,
    LoanPayment,
    LoanRule,
)


DECIDERS = ("admin", "loan_officer")
PAYMENT_TAKERS = ("admin", "staff")


def _require_role(user, allowed, message):
    if user.role.name not in allowed:
        raise BankError(message)


def _get_loan_locked(loan_id):
    try:
        return Loan.objects.select_for_update().get(pk=loan_id)
    except Loan.DoesNotExist:
        raise BankError("Loan not found.")


def _age_on_date(birthdate, today):
    return (
        today.year - birthdate.year
        - ((today.month, today.day) < (birthdate.month, birthdate.day))
    )


# --------------------------------------------------
# BLOCK CLIENTS WITH OVERDUE LOANS
# --------------------------------------------------

def check_overdue_loans(client):
    today = timezone.localdate()

    has_overdue = (
        Installment.objects.filter(
            loan__client=client,
            loan__status=Loan.Status.ACTIVE,
            due_date__lt=today,
        )
        .exclude(status=Installment.Status.PAID)
        .exists()
    )

    if has_overdue:
        raise BankError(
            "Client cannot apply for a new loan because "
            "they have an overdue installment."
        )


# --------------------------------------------------
# LOAN ELIGIBILITY CHECK
# --------------------------------------------------

@transaction.atomic
def check_eligibility(loan_id, by):
    loan = _get_loan_locked(loan_id)

    _require_role(
        by,
        DECIDERS,
        "You are not allowed to check loan eligibility.",
    )

    rule = LoanRule.objects.filter(
        product=loan.product,
        is_active=True,
    ).first()

    if rule is None:
        result = EligibilityCheck.Result.REVIEW
        remarks = "No active eligibility rule is configured."

    else:
        client = loan.client
        reasons = []
        missing = []

        if not client.date_of_birth:
            missing.append("Date of birth is missing.")

        elif _age_on_date(
            client.date_of_birth,
            timezone.localdate(),
        ) < rule.minimum_age:
            reasons.append(
                "Client does not meet the minimum age."
            )

        if client.monthly_income is None:
            missing.append("Monthly income is missing.")

        elif client.monthly_income < rule.minimum_monthly_income:
            reasons.append(
                "Monthly income is below the requirement."
            )

        if client.credit_score is None:
            missing.append("Credit score is missing.")

        elif client.credit_score < rule.minimum_credit_score:
            reasons.append(
                "Credit score is below the requirement."
            )

        if client.monthly_income is not None:
            installment = monthly_installment(
                loan.principal,
                loan.annual_rate,
                loan.term_months,
            )

            income_limit = (
                client.monthly_income * Decimal("0.40")
            )

            if installment > income_limit:
                reasons.append(
                    "Monthly loan installment exceeds "
                    "40% of the client's monthly income."
                )

        required_savings = (
            loan.principal * Decimal("0.10")
        )

        total_savings = sum(
            (
                account.balance
                for account in SavingsAccount.objects.filter(
                    client=client,
                    status=SavingsAccount.Status.ACTIVE,
                )
            ),
            Decimal("0.00"),
        )

        if total_savings < required_savings:
            reasons.append(
                "Client does not have enough savings. "
                "Savings must be at least 10% "
                "of the requested loan amount."
            )

        if reasons:
            result = EligibilityCheck.Result.INELIGIBLE
            remarks = " ".join(reasons + missing)

        elif missing:
            result = EligibilityCheck.Result.REVIEW
            remarks = " ".join(missing)

        else:
            result = EligibilityCheck.Result.ELIGIBLE
            remarks = (
                "Client meets all configured "
                "eligibility requirements."
            )

    record = EligibilityCheck.objects.create(
        loan=loan,
        result=result,
        remarks=remarks,
        checked_by=by,
    )

    log(
        by,
        "loan_eligibility_check",
        loan,
        result=result,
    )

    return record


# --------------------------------------------------
# APPLY FOR A LOAN
# --------------------------------------------------

@transaction.atomic
def apply_for_loan(client, product, principal, term_months, by):
    principal = to_money(principal)

    try:
        term_months = int(term_months)
    except (TypeError, ValueError):
        raise BankError("Enter a valid number of months.")

    if not product.is_active:
        raise BankError("This loan product is not available.")

    if not (
        product.min_amount <= principal <= product.max_amount
    ):
        raise BankError(
            f"Amount must be between "
            f"{product.min_amount} and {product.max_amount}."
        )

    if not (
        product.min_months <= term_months <= product.max_months
    ):
        raise BankError(
            f"Term must be between "
            f"{product.min_months} and {product.max_months} months."
        )

    check_overdue_loans(client)

    loan = Loan.objects.create(
        client=client,
        product=product,
        principal=principal,
        annual_rate=product.annual_rate,
        term_months=term_months,
    )

    log(
        by,
        "loan_apply",
        loan,
        principal=principal,
        term_months=term_months,
    )

    Notification.objects.create(
        user=client.user,
        kind="loan_application",
        message=(
            f"Loan application #{loan.pk} "
            f"was submitted successfully."
        ),
    )

    return loan


# --------------------------------------------------
# APPROVE LOAN
# --------------------------------------------------

@transaction.atomic
def approve_loan(loan_id, by):
    _require_role(
        by,
        DECIDERS,
        "You are not allowed to approve loans.",
    )

    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.PENDING:
        raise BankError(
            f"Only pending loans can be approved "
            f"(this one is {loan.status})."
        )

    if loan.client.user_id == by.pk:
        raise BankError(
            "You cannot approve your own loan."
        )

    latest_check = (
        EligibilityCheck.objects.filter(loan=loan)
        .order_by("-pk")
        .first()
    )

    if latest_check is None:
        raise BankError(
            "Loan eligibility must be checked before approval."
        )

    if latest_check.result == EligibilityCheck.Result.INELIGIBLE:
        raise BankError(
            "This loan cannot be approved because "
            "the client is not eligible."
        )

    if latest_check.result == EligibilityCheck.Result.REVIEW:
        raise BankError(
            "This loan needs further review before approval."
        )

    if latest_check.result != EligibilityCheck.Result.ELIGIBLE:
        raise BankError(
            "Loan eligibility result is not valid for approval."
        )

    loan.status = Loan.Status.APPROVED
    loan.decided_by = by
    loan.decided_at = timezone.now()

    loan.save(
        update_fields=[
            "status",
            "decided_by",
            "decided_at",
        ]
    )

    log(by, "loan_approve", loan)

    Notification.objects.create(
        user=loan.client.user,
        kind="loan_approved",
        message=(
            f"Loan application #{loan.pk} "
            f"has been approved."
        ),
    )

    return loan


# --------------------------------------------------
# REJECT LOAN
# --------------------------------------------------

@transaction.atomic
def reject_loan(loan_id, by, reason):
    _require_role(
        by,
        DECIDERS,
        "You are not allowed to reject loans.",
    )

    reason = (reason or "").strip()

    if not reason:
        raise BankError(
            "A reason is required to reject a loan."
        )

    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.PENDING:
        raise BankError(
            f"Only pending loans can be rejected "
            f"(this one is {loan.status})."
        )

    loan.status = Loan.Status.REJECTED
    loan.decided_by = by
    loan.decided_at = timezone.now()
    loan.reject_reason = reason[:255]

    loan.save(
        update_fields=[
            "status",
            "decided_by",
            "decided_at",
            "reject_reason",
        ]
    )

    log(
        by,
        "loan_reject",
        loan,
        reason=reason,
    )

    Notification.objects.create(
        user=loan.client.user,
        kind="loan_rejected",
        message=(
            f"Loan application #{loan.pk} was rejected. "
            f"Reason: {loan.reject_reason}"
        )[:255],
    )

    return loan


# --------------------------------------------------
# CREATE LOAN AGREEMENT
# --------------------------------------------------

@transaction.atomic
def create_loan_agreement(
    loan_id,
    agreement_number,
    agreement_date,
    terms_and_conditions="",
):
    loan = _get_loan_locked(loan_id)

    if loan.status not in (
        Loan.Status.APPROVED,
        Loan.Status.ACTIVE,
    ):
        raise BankError(
            "Only approved or active loans can have agreements."
        )

    if not agreement_number or not agreement_number.strip():
        raise BankError(
            "Agreement number is required."
        )

    if not agreement_date:
        raise BankError(
            "Agreement date is required."
        )

    if hasattr(loan, "agreement"):
        raise BankError(
            "This loan already has an agreement."
        )

    return LoanAgreement.objects.create(
        loan=loan,
        agreement_number=agreement_number.strip(),
        agreement_date=agreement_date,
        terms_and_conditions=terms_and_conditions,
    )


# --------------------------------------------------
# ACCEPT LOAN AGREEMENT
# --------------------------------------------------

@transaction.atomic
def accept_loan_agreement(loan_id, by):
    loan = _get_loan_locked(loan_id)

    if loan.client.user_id != by.pk:
        raise BankError(
            "You cannot accept another client's loan agreement."
        )

    if loan.status != Loan.Status.APPROVED:
        raise BankError(
            "Only approved loans can have their agreements accepted."
        )

    try:
        agreement = LoanAgreement.objects.select_for_update().get(
            loan=loan
        )
    except LoanAgreement.DoesNotExist:
        raise BankError(
            "No loan agreement has been generated for this loan."
        )

    if agreement.signed_at is not None:
        raise BankError(
            "This loan agreement has already been accepted."
        )

    agreement.signed_at = timezone.now()
    agreement.save(update_fields=["signed_at"])

    log(
        by,
        "loan_agreement_accept",
        loan,
        agreement_number=agreement.agreement_number,
    )

    Notification.objects.create(
        user=loan.client.user,
        kind="loan_agreement_accepted",
        message=(
            f"Loan agreement {agreement.agreement_number} "
            f"for loan #{loan.pk} has been accepted."
        ),
    )

    return agreement


# --------------------------------------------------
# DISBURSE LOAN TO REGULAR BANK ACCOUNT
# --------------------------------------------------

@transaction.atomic
def disburse_loan(loan_id, by, bank_account_id):
    _require_role(
        by,
        DECIDERS,
        "You are not allowed to disburse loans.",
    )

    loan = _get_loan_locked(loan_id)

    # Only approved loans can be disbursed.
    if loan.status != Loan.Status.APPROVED:
        raise BankError(
            f"Only approved loans can be disbursed "
            f"(this one is {loan.status})."
        )

    # Prevent duplicate disbursement records.
    if Disbursement.objects.filter(loan=loan).exists():
        raise BankError(
            "This loan has already been disbursed."
        )

    # The client must accept the agreement first.
    try:
        agreement = LoanAgreement.objects.select_for_update().get(
            loan=loan
        )
    except LoanAgreement.DoesNotExist:
        raise BankError(
            "Generate a loan agreement before disbursement."
        )

    if agreement.signed_at is None:
        raise BankError(
            "The client must accept the loan agreement "
            "before disbursement."
        )

    # Find and lock the regular bank account.
    try:
        account = (
            BankAccount.objects
            .select_for_update()
            .get(pk=bank_account_id)
        )
    except (BankAccount.DoesNotExist, ValueError, TypeError):
        raise BankError(
            "Regular bank account not found."
        )

    # Verify that the account belongs to the borrower.
    if account.client_id != loan.client_id:
        raise BankError(
            "That bank account does not belong to "
            "the loan's client."
        )

    # Frozen and closed accounts cannot receive disbursements.
    if account.status != BankAccount.Status.ACTIVE:
        raise BankError(
            f"Bank account {account.account_number} "
            f"is {account.status}."
        )

    today = timezone.localdate()

    # Create the repayment schedule.
    rows = build_schedule(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
        today,
    )

    Installment.objects.bulk_create([
        Installment(
            loan=loan,
            number=row["number"],
            due_date=row["due_date"],
            principal_due=row["principal_due"],
            interest_due=row["interest_due"],
        )
        for row in rows
    ])

    # Credit the REGULAR BANK ACCOUNT, not savings.
    account.balance += loan.principal
    account.save(update_fields=["balance"])

    # Record the disbursement in the accounting ledger.
    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.LOAN_DISBURSEMENT,
        amount=loan.principal,
        balance_after=account.balance,
        bank_account=account,
        loan=loan,
        created_by=by,
    )

    # Link the loan to the destination bank account.
    Disbursement.objects.create(
        loan=loan,
        bank_account=account,
        ledger_entry=entry,
        amount=loan.principal,
        disbursed_by=by,
    )

    # Activate the loan.
    loan.status = Loan.Status.ACTIVE
    loan.disbursed_at = timezone.now()
    loan.start_date = today

    loan.save(
        update_fields=[
            "status",
            "disbursed_at",
            "start_date",
        ]
    )

    log(
        by,
        "loan_disburse",
        loan,
        account=account.account_number,
        amount=loan.principal,
    )

    Notification.objects.create(
        user=loan.client.user,
        kind="loan_disbursed",
        message=(
            f"Loan #{loan.pk} was disbursed successfully "
            f"to bank account {account.account_number}."
        ),
    )

    return loan


# --------------------------------------------------
# RECORD LOAN PAYMENT
# --------------------------------------------------

@transaction.atomic
def record_payment(loan_id, amount, by):
    _require_role(
        by,
        PAYMENT_TAKERS,
        "You are not allowed to record loan payments.",
    )

    amount = to_money(amount)
    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.ACTIVE:
        raise BankError(
            f"Payments can only be recorded on active loans "
            f"(this one is {loan.status})."
        )

    unpaid = list(
        loan.installments.select_for_update()
        .exclude(status=Installment.Status.PAID)
        .order_by("number")
    )

    remaining = sum(
        (
            inst.total_due - inst.amount_paid
            for inst in unpaid
        ),
        start=Decimal("0.00"),
    )

    if amount > remaining:
        raise BankError(
            f"Payment is more than the remaining balance "
            f"({remaining})."
        )

    now = timezone.now()
    left = amount

    for inst in unpaid:
        pay = min(
            inst.total_due - inst.amount_paid,
            left,
        )

        inst.amount_paid += pay

        if inst.amount_paid >= inst.total_due:
            inst.status = Installment.Status.PAID
            inst.paid_at = now

        inst.save(
            update_fields=[
                "amount_paid",
                "status",
                "paid_at",
            ]
        )

        left -= pay

        if left == 0:
            break

    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.LOAN_PAYMENT,
        amount=amount,
        loan=loan,
        created_by=by,
    )

    LoanPayment.objects.create(
        loan=loan,
        ledger_entry=entry,
        amount=amount,
        recorded_by=by,
    )

    if amount == remaining:
        loan.status = Loan.Status.PAID
        loan.save(update_fields=["status"])

    log(
        by,
        "loan_payment",
        loan,
        amount=amount,
    )

    Notification.objects.create(
        user=loan.client.user,
        kind="loan_payment",
        message=(
            f"Payment of PHP {amount:,.2f} "
            f"was recorded for loan #{loan.pk}."
        ),
    )

    return entry
