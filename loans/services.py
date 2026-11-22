from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Role, User
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.services import log
from notifications.models import Notification
from savings.models import SavingsAccount

from .calculations import build_schedule
from .models import (
    Disbursement,
    EligibilityCheck,
    Installment,
    Loan,
    LoanAgreement,
    LoanPayment,
    LoanRule,
)


# --------------------------------------------------
# PERMISSIONS AND DEFAULT ELIGIBILITY RULES
# --------------------------------------------------

DECIDERS = ("admin", "loan_officer")
DISBURSERS = ("admin", "staff")
PAYMENT_TAKERS = ("admin", "staff")

INTERNAL_NOTIFICATION_ROLES = (
    Role.ADMIN,
    Role.STAFF,
    Role.LOAN_OFFICER,
)

DEFAULT_MAX_INSTALLMENT_RATIO = Decimal("0.40")
DEFAULT_MIN_SAVINGS_RATIO = Decimal("0.10")
DEFAULT_MINIMUM_AGE = 18


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def _require_role(user, allowed, message):
    role_name = getattr(
        getattr(user, "role", None),
        "name",
        None,
    )

    if role_name not in allowed:
        raise BankError(message)


def _get_loan_locked(loan_id):
    try:
        return Loan.objects.select_for_update().get(pk=loan_id)
    except Loan.DoesNotExist:
        raise BankError("Loan not found.")


def _notify_loan_parties(
    loan,
    kind,
    client_message,
    staff_message=None,
    exclude_user=None,
):
    """
    Notify the borrower and active internal users.

    The borrower receives the client-specific message.
    Internal users receive the staff-specific message.

    The user performing the action is excluded from internal
    notifications to avoid notifying them about their own action.

    Notifications are created within the current transaction.
    """

    recipients = {
        loan.client.user_id: (
            loan.client.user,
            client_message[:255],
        )
    }

    internal_users = User.objects.filter(
        is_active=True,
        role__name__in=INTERNAL_NOTIFICATION_ROLES,
    ).exclude(
        pk=loan.client.user_id,
    )

    if exclude_user is not None:
        internal_users = internal_users.exclude(
            pk=exclude_user.pk,
        )

    internal_message = (
        staff_message or client_message
    )[:255]

    for user in internal_users:
        recipients[user.pk] = (
            user,
            internal_message,
        )

    Notification.objects.bulk_create([
        Notification(
            user=user,
            kind=kind,
            message=message,
        )
        for user, message in recipients.values()
    ])


def _calculate_age(date_of_birth, today=None):
    """Calculate age using the client's date of birth."""

    if not date_of_birth:
        return None

    today = today or timezone.localdate()

    age = today.year - date_of_birth.year

    if (today.month, today.day) < (
        date_of_birth.month,
        date_of_birth.day,
    ):
        age -= 1

    return age


def _save_eligibility_result(loan, checked_by, result, remarks):
    """Save an eligibility result and its audit event."""

    record = EligibilityCheck.objects.create(
        loan=loan,
        result=result,
        remarks=remarks,
        checked_by=checked_by,
    )

    log(
        checked_by,
        "loan_eligibility_check",
        loan,
        result=result,
    )

    return record


# --------------------------------------------------
# LOAN ELIGIBILITY
# --------------------------------------------------

def _evaluate(loan, checked_by):
    """
    Evaluate a loan application using its product's eligibility rules.

    Results:
    - ELIGIBLE: All applicable criteria are satisfied.
    - REVIEW: A failed criterion or missing information needs review.
    - INELIGIBLE: Two or more criteria fail.
    """

    rule = LoanRule.objects.filter(
        product=loan.product,
    ).first()

    if rule and not rule.is_active:
        return _save_eligibility_result(
            loan,
            checked_by,
            EligibilityCheck.Result.REVIEW,
            (
                "The eligibility rules for this loan product are inactive. "
                "Manual review is required before a decision can be made."
            ),
        )

    max_ratio = (
        rule.max_installment_ratio
        if rule else DEFAULT_MAX_INSTALLMENT_RATIO
    )

    min_savings_ratio = (
        rule.min_savings_ratio
        if rule else DEFAULT_MIN_SAVINGS_RATIO
    )

    minimum_income = (
        rule.minimum_monthly_income
        if rule else Decimal("0.00")
    )

    minimum_age = (
        rule.minimum_age
        if rule else DEFAULT_MINIMUM_AGE
    )

    minimum_score = (
        rule.minimum_credit_score
        if rule else 0
    )

    client = loan.client
    today = timezone.localdate()

    rows = build_schedule(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
        today,
    )

    if not rows:
        raise BankError(
            "Unable to calculate the loan repayment schedule."
        )

    installment = max(
        row["principal_due"] + row["interest_due"]
        for row in rows
    )

    income = client.monthly_income or Decimal("0.00")

    savings = (
        SavingsAccount.objects.filter(
            client=client,
            status=SavingsAccount.Status.ACTIVE,
        ).aggregate(total=Sum("balance"))["total"]
        or Decimal("0.00")
    )

    score = client.credit_score or 0
    age = _calculate_age(client.date_of_birth, today)

    failed = []
    needs_review = []

    # 1. Minimum age
    if age is None:
        needs_review.append(
            "Age: date of birth is missing. Verify the client's age."
        )
    elif age < minimum_age:
        failed.append(
            f"Age: client is {age} years old, below the required "
            f"minimum age of {minimum_age}."
        )

    # 2. Minimum monthly income
    if income < minimum_income:
        failed.append(
            f"Minimum income: monthly income of P{income:,.2f} "
            f"is below the required P{minimum_income:,.2f}."
        )

    # 3. Monthly installment affordability
    if income <= Decimal("0.00"):
        if not any("Minimum income:" in item for item in failed):
            needs_review.append(
                "Income: monthly income is zero or unavailable. "
                "Verify the client's income."
            )

    elif installment > income * max_ratio:
        failed.append(
            f"Income affordability: monthly installment "
            f"P{installment:,.2f} exceeds {max_ratio:.0%} "
            f"of monthly income P{income:,.2f}."
        )

    # 4. Savings requirement
    required_savings = loan.principal * min_savings_ratio

    if savings < required_savings:
        failed.append(
            f"Savings: balance P{savings:,.2f} is below the required "
            f"P{required_savings:,.2f} ({min_savings_ratio:.0%} "
            "of the loan amount)."
        )

    # 5. Minimum credit score
    if minimum_score > 0 and score <= 0:
        needs_review.append(
            "Credit score: no usable credit score is recorded. "
            "Verify the client's credit information."
        )

    elif score < minimum_score:
        failed.append(
            f"Credit score: {score} is below the required minimum "
            f"of {minimum_score}."
        )

    # Determine eligibility result
    if len(failed) >= 2:
        result = EligibilityCheck.Result.INELIGIBLE
        remarks = (
            "Multiple eligibility criteria failed. "
            + " ".join(failed)
        )

    elif failed:
        result = EligibilityCheck.Result.REVIEW
        remarks = (
            "One eligibility criterion failed. "
            + " ".join(failed)
        )

        if needs_review:
            remarks += " " + " ".join(needs_review)

    elif needs_review:
        result = EligibilityCheck.Result.REVIEW
        remarks = (
            "Additional verification is required. "
            + " ".join(needs_review)
        )

    else:
        result = EligibilityCheck.Result.ELIGIBLE
        remarks = "All eligibility criteria were satisfied."

    return _save_eligibility_result(
        loan,
        checked_by,
        result,
        remarks,
    )


# --------------------------------------------------
# BLOCK CLIENTS WITH OVERDUE LOANS
# --------------------------------------------------

def check_overdue_loans(client):
    """
    Prevent clients with overdue active loans from applying
    for another loan.
    """

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
    """Allow a loan officer or admin to reassess eligibility."""

    _require_role(
        by,
        DECIDERS,
        "You are not allowed to check loan eligibility.",
    )

    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.PENDING:
        raise BankError(
            "Eligibility can only be reassessed for pending loans."
        )

    return _evaluate(loan, by)


# --------------------------------------------------
# APPLY FOR A LOAN
# --------------------------------------------------

@transaction.atomic
def apply_for_loan(
    client,
    product,
    principal,
    term_months,
    by,
    purpose="",
):
    """Create a loan application and perform its initial assessment."""

    try:
        principal = to_money(principal)
    except (TypeError, ValueError):
        raise BankError("Enter a valid loan amount.")

    if principal <= 0:
        raise BankError("Loan amount must be greater than zero.")

    try:
        term_months = int(term_months)
    except (TypeError, ValueError):
        raise BankError("Enter a valid number of months.")

    purpose = (purpose or "").strip()

    if not purpose:
        raise BankError(
            "Please provide the purpose of your loan application."
        )

    if len(purpose) > 1000:
        raise BankError(
            "Loan purpose cannot exceed 1,000 characters."
        )

    if not product.is_active:
        raise BankError("This loan product is not available.")

    if not (
        product.min_amount <= principal <= product.max_amount
    ):
        raise BankError(
            f"Amount must be between {product.min_amount} "
            f"and {product.max_amount}."
        )

    if not (
        product.min_months <= term_months <= product.max_months
    ):
        raise BankError(
            f"Term must be between {product.min_months} "
            f"and {product.max_months} months."
        )

    check_overdue_loans(client)

    loan = Loan.objects.create(
        client=client,
        product=product,
        principal=principal,
        annual_rate=product.annual_rate,
        term_months=term_months,
        purpose=purpose,
    )

    log(
        by,
        "loan_apply",
        loan,
        principal=principal,
        term_months=term_months,
        purpose=purpose,
    )

    # Perform the initial eligibility assessment.
    _evaluate(loan, None)

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_APPLICATION_SUBMITTED,
        (
            f"Your loan application for P{loan.principal:,.2f} "
            "has been submitted successfully."
        ),
        (
            f"New loan application from "
            f"{loan.client.user.get_username()} for "
            f"P{loan.principal:,.2f}. "
            f"Application ID: {loan.pk}."
        ),
        exclude_user=by,
    )

    return loan


# --------------------------------------------------
# APPROVE LOAN
# --------------------------------------------------

@transaction.atomic
def approve_loan(loan_id, by):
    """Approve an eligible pending loan."""

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
        raise BankError("You cannot approve your own loan.")

    # Always perform a fresh eligibility assessment.
    latest_check = _evaluate(loan, by)

    if latest_check.result == EligibilityCheck.Result.INELIGIBLE:
        raise BankError(
            "This loan cannot be approved because the client "
            "failed multiple eligibility criteria."
        )

    if latest_check.result == EligibilityCheck.Result.REVIEW:
        raise BankError(
            "This loan requires additional verification. "
            "Resolve the eligibility concerns and reassess it "
            "before approval."
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

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_APPROVED,
        (
            f"Your loan application for P{loan.principal:,.2f} "
            "has been approved. Please review your loan agreement."
        ),
        (
            f"Loan application #{loan.pk} for "
            f"{loan.client.user.get_username()} "
            f"(P{loan.principal:,.2f}) has been approved."
        ),
        exclude_user=by,
    )

    log(by, "loan_approve", loan)

    return loan


# --------------------------------------------------
# REJECT LOAN
# --------------------------------------------------

@transaction.atomic
def reject_loan(loan_id, by, reason):
    """Reject a pending loan application."""

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

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_REJECTED,
        (
            f"Your loan application for P{loan.principal:,.2f} "
            f"was rejected. Reason: {reason}"
        ),
        (
            f"Loan application #{loan.pk} for "
            f"{loan.client.user.get_username()} "
            f"(P{loan.principal:,.2f}) was rejected."
        ),
        exclude_user=by,
    )

    log(
        by,
        "loan_reject",
        loan,
        reason=reason,
    )

    return loan


# --------------------------------------------------
# LOAN AGREEMENT
# --------------------------------------------------

@transaction.atomic
def create_loan_agreement(
    loan_id,
    agreement_number,
    agreement_date,
    terms_and_conditions="",
):
    """Generate an agreement for an approved loan."""

    loan = _get_loan_locked(loan_id)

    if loan.status not in (
        Loan.Status.APPROVED,
        Loan.Status.ACTIVE,
    ):
        raise BankError(
            "Only approved or active loans can have agreements."
        )

    if not agreement_number or not agreement_number.strip():
        raise BankError("Agreement number is required.")

    if not agreement_date:
        raise BankError("Agreement date is required.")

    if LoanAgreement.objects.filter(loan=loan).exists():
        raise BankError(
            "This loan already has an agreement."
        )

    agreement = LoanAgreement.objects.create(
        loan=loan,
        agreement_number=agreement_number.strip(),
        agreement_date=agreement_date,
        terms_and_conditions=terms_and_conditions,
    )

    _notify_loan_parties(
        loan,
        Notification.Kind.AGREEMENT_READY,
        (
            f"Your loan agreement {agreement.agreement_number} "
            "is ready. Please sign in to review and accept it."
        ),
        (
            f"Agreement {agreement.agreement_number} was created "
            f"for loan #{loan.pk} belonging to "
            f"{loan.client.user.get_username()}."
        ),
    )

    return agreement


@transaction.atomic
def accept_loan_agreement(loan_id, by):
    """
    Allow the borrower to accept their loan agreement.

    The agreement must be accepted before disbursement.
    """

    loan = _get_loan_locked(loan_id)

    if loan.client.user_id != by.pk:
        raise BankError(
            "Only the borrower can accept this agreement."
        )

    if loan.status != Loan.Status.APPROVED:
        raise BankError(
            "Only approved loans have an agreement to accept."
        )

    agreement = (
        LoanAgreement.objects.select_for_update()
        .filter(loan=loan)
        .first()
    )

    if agreement is None:
        raise BankError(
            "This loan has no agreement yet."
        )

    if agreement.signed_at:
        raise BankError(
            "This agreement was already accepted."
        )

    agreement.signed_at = timezone.now()
    agreement.save(update_fields=["signed_at"])

    log(
        by,
        "loan_agreement_accept",
        loan,
        agreement_number=agreement.agreement_number,
    )

    _notify_loan_parties(
        loan,
        Notification.Kind.AGREEMENT_ACCEPTED,
        (
            "Your acceptance of the loan agreement "
            "has been recorded."
        ),
        (
            f"{loan.client.user.get_username()} accepted "
            f"the agreement for loan #{loan.pk}."
        ),
    )

    return agreement


# --------------------------------------------------
# DISBURSE LOAN TO REGULAR BANK ACCOUNT
# --------------------------------------------------

@transaction.atomic
def disburse_loan(loan_id, by, bank_account_id):
    """
    Disburse an approved loan into the borrower's regular bank account.

    The borrower must accept the loan agreement first.
    Loan proceeds never go directly into the savings account.
    """

    _require_role(
        by,
        DISBURSERS,
        "You are not allowed to disburse loans.",
    )

    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.APPROVED:
        raise BankError(
            f"Only approved loans can be disbursed "
            f"(this one is {loan.status})."
        )

    if Disbursement.objects.filter(loan=loan).exists():
        raise BankError(
            "This loan already has a disbursement record."
        )

    agreement = (
        LoanAgreement.objects.select_for_update()
        .filter(loan=loan)
        .first()
    )

    if agreement is None:
        raise BankError(
            "A loan agreement must be created before disbursement."
        )

    if agreement.signed_at is None:
        raise BankError(
            "The borrower must accept the loan agreement "
            "before disbursement."
        )

    try:
        account = (
            BankAccount.objects.select_for_update()
            .get(pk=bank_account_id)
        )
    except BankAccount.DoesNotExist:
        raise BankError("Bank account not found.")

    if account.client_id != loan.client_id:
        raise BankError(
            "That bank account does not belong to the loan's client."
        )

    if account.status != BankAccount.Status.ACTIVE:
        raise BankError(
            f"Bank account {account.account_number} "
            f"is {account.status}."
        )

    today = timezone.localdate()

    rows = build_schedule(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
        today,
    )

    if not rows:
        raise BankError(
            "Unable to generate the loan repayment schedule."
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

    # Credit the regular bank account.
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

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_DISBURSED,
        (
            f"Your loan of P{loan.principal:,.2f} has been disbursed "
            f"to your bank account {account.account_number}."
        ),
        (
            f"Loan #{loan.pk} for "
            f"{loan.client.user.get_username()} has been disbursed. "
            f"Amount: P{loan.principal:,.2f}."
        ),
        exclude_user=by,
    )

    log(
        by,
        "loan_disburse",
        loan,
        account=account.account_number,
        amount=loan.principal,
        destination="bank_account",
    )

    return loan


# --------------------------------------------------
# SHARED INSTALLMENT ALLOCATION
# --------------------------------------------------

def _allocate_payment_to_installments(loan, amount):
    """
    Allocate a payment to the oldest unpaid installments first.

    Returns the remaining loan balance after the payment.
    """

    unpaid = list(
        loan.installments.select_for_update()
        .exclude(status=Installment.Status.PAID)
        .order_by("number")
    )

    if not unpaid:
        raise BankError(
            "This loan has no outstanding installments."
        )

    remaining = sum(
        (
            installment.total_due - installment.amount_paid
            for installment in unpaid
        ),
        start=Decimal("0.00"),
    )

    if remaining <= Decimal("0.00"):
        raise BankError(
            "This loan has no remaining balance to collect."
        )

    if amount > remaining:
        raise BankError(
            f"Payment exceeds the remaining balance "
            f"of P{remaining:,.2f}."
        )

    now = timezone.now()
    left = amount

    for installment in unpaid:
        outstanding = (
            installment.total_due - installment.amount_paid
        )

        if outstanding <= Decimal("0.00"):
            continue

        payment_amount = min(outstanding, left)

        installment.amount_paid += payment_amount

        if installment.amount_paid >= installment.total_due:
            installment.amount_paid = installment.total_due
            installment.status = Installment.Status.PAID
            installment.paid_at = now

        installment.save(
            update_fields=[
                "amount_paid",
                "status",
                "paid_at",
            ]
        )

        left -= payment_amount

        if left == Decimal("0.00"):
            break

    if left != Decimal("0.00"):
        raise BankError(
            "The payment could not be fully allocated "
            "to the installments."
        )

    return remaining - amount


def _complete_loan_if_paid(loan, remaining_balance):
    """Mark the loan as paid when no balance remains."""

    if remaining_balance == Decimal("0.00"):
        loan.status = Loan.Status.PAID
        loan.save(update_fields=["status"])
        return True

    return False


# --------------------------------------------------
# RECORD LOAN PAYMENT - STAFF
# --------------------------------------------------

@transaction.atomic
def record_payment(loan_id, amount, by):
    """
    Allow authorized staff to record a loan repayment.

    This function records a payment against the loan.
    It does not directly debit the borrower's bank account.
    """

    _require_role(
        by,
        PAYMENT_TAKERS,
        "You are not allowed to record loan payments.",
    )

    try:
        amount = to_money(amount)
    except (TypeError, ValueError):
        raise BankError("Enter a valid payment amount.")

    if amount <= Decimal("0.00"):
        raise BankError(
            "Payment amount must be greater than zero."
        )

    loan = _get_loan_locked(loan_id)

    if loan.status != Loan.Status.ACTIVE:
        raise BankError(
            f"Payments can only be recorded on active loans "
            f"(this one is {loan.status})."
        )

    remaining_after_payment = _allocate_payment_to_installments(
        loan,
        amount,
    )

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

    loan_fully_paid = _complete_loan_if_paid(
        loan,
        remaining_after_payment,
    )

    if loan_fully_paid:
        payment_message = (
            f"Your final loan payment of P{amount:,.2f} "
            "has been recorded. Your loan is now fully paid."
        )

        staff_payment_message = (
            f"Loan #{loan.pk} for "
            f"{loan.client.user.get_username()} is now fully paid. "
            f"Final payment: P{amount:,.2f}."
        )

    else:
        payment_message = (
            f"Your loan payment of P{amount:,.2f} has been recorded. "
            f"Remaining balance: P{remaining_after_payment:,.2f}."
        )

        staff_payment_message = (
            f"Payment of P{amount:,.2f} recorded for loan #{loan.pk} "
            f"belonging to {loan.client.user.get_username()}. "
            f"Remaining balance: P{remaining_after_payment:,.2f}."
        )

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_PAYMENT_RECORDED,
        payment_message,
        staff_payment_message,
        exclude_user=by,
    )

    log(
        by,
        "loan_payment",
        loan,
        amount=amount,
        remaining_balance=remaining_after_payment,
    )

    return entry


# --------------------------------------------------
# CLIENT ONLINE LOAN PAYMENT
# --------------------------------------------------

@transaction.atomic
def make_online_payment(loan_id, amount, by):
    """
    Allow a borrower to repay an active loan online.

    The payment is deducted from the borrower's regular bank account.

    The bank debit, ledger entry, loan payment, and installment updates
    are committed together or rolled back together.
    """

    if not getattr(by, "is_authenticated", False):
        raise BankError(
            "Please log in to make a loan payment."
        )

    try:
        amount = to_money(amount)
    except (TypeError, ValueError):
        raise BankError("Enter a valid payment amount.")

    if amount <= Decimal("0.00"):
        raise BankError(
            "Payment amount must be greater than zero."
        )

    loan = _get_loan_locked(loan_id)

    if loan.client.user_id != by.pk:
        raise BankError(
            "You are not authorized to pay this loan."
        )

    if loan.status != Loan.Status.ACTIVE:
        raise BankError(
            "Online payments are only allowed for active loans."
        )

    try:
        account = (
            BankAccount.objects.select_for_update()
            .get(client_id=loan.client_id)
        )
    except BankAccount.DoesNotExist:
        raise BankError(
            "You do not have a regular bank account for this payment."
        )

    if account.status != BankAccount.Status.ACTIVE:
        raise BankError(
            "Your bank account is not active. Please contact the bank."
        )

    if account.balance < amount:
        raise BankError(
            f"Insufficient funds. Your available balance is "
            f"P{account.balance:,.2f}."
        )

    # Allocate the payment to installments first.
    remaining_after_payment = _allocate_payment_to_installments(
        loan,
        amount,
    )

    # Debit the regular bank account.
    account.balance -= amount
    account.save(update_fields=["balance"])

    # Record the debit in the accounting ledger.
    entry = LedgerEntry.objects.create(
        entry_type=LedgerEntry.EntryType.LOAN_PAYMENT,
        amount=amount,
        balance_after=account.balance,
        bank_account=account,
        loan=loan,
        created_by=by,
    )

    # Record the loan payment.
    LoanPayment.objects.create(
        loan=loan,
        ledger_entry=entry,
        amount=amount,
        recorded_by=by,
    )

    loan_fully_paid = _complete_loan_if_paid(
        loan,
        remaining_after_payment,
    )

    if loan_fully_paid:
        payment_message = (
            f"Your online loan payment of P{amount:,.2f} "
            "was successful. Your loan is now fully paid."
        )

        staff_payment_message = (
            f"Loan #{loan.pk} for "
            f"{loan.client.user.get_username()} is now fully paid "
            f"through an online payment of P{amount:,.2f}."
        )

    else:
        payment_message = (
            f"Your online loan payment of P{amount:,.2f} "
            "was successful. "
            f"Remaining loan balance: P{remaining_after_payment:,.2f}."
        )

        staff_payment_message = (
            f"Online loan payment of P{amount:,.2f} received for "
            f"loan #{loan.pk}, belonging to "
            f"{loan.client.user.get_username()}. "
            f"Remaining balance: P{remaining_after_payment:,.2f}."
        )

    _notify_loan_parties(
        loan,
        Notification.Kind.LOAN_PAYMENT_RECORDED,
        payment_message,
        staff_payment_message,
        exclude_user=by,
    )

    log(
        by,
        "loan_online_payment",
        loan,
        amount=amount,
        bank_account=account.account_number,
        remaining_balance=remaining_after_payment,
        balance_after=account.balance,
    )

    return entry