
from django.conf import settings
from django.db import models
from django.db.models import F, Q


# ==========================================
# 1. LOAN PRODUCTS
# ==========================================

class LoanProduct(models.Model):
    name = models.CharField(max_length=100, unique=True)

    annual_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    min_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    max_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    min_months = models.PositiveSmallIntegerField()
    max_months = models.PositiveSmallIntegerField()

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(annual_rate__gte=0),
                name="loan_product_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(min_amount__gt=0),
                name="loan_product_min_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(max_amount__gte=F("min_amount")),
                name="loan_product_valid_amount_range",
            ),
            models.CheckConstraint(
                condition=Q(min_months__gte=1),
                name="loan_product_min_term_positive",
            ),
            models.CheckConstraint(
                condition=Q(max_months__gte=F("min_months")),
                name="loan_product_valid_term_range",
            ),
        ]

    def __str__(self):
        return self.name


# ==========================================
# 2. LOAN APPLICATIONS AND RECORDS
# ==========================================

class Loan(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ACTIVE = "active", "Active"
        PAID = "paid", "Paid"
        DEFAULTED = "defaulted", "Defaulted"

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="loans",
    )

    product = models.ForeignKey(
        LoanProduct,
        on_delete=models.PROTECT,
    )

    principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    annual_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    term_months = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    applied_at = models.DateTimeField(auto_now_add=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    decided_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    reject_reason = models.CharField(
        max_length=255,
        blank=True,
    )

    disbursed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    start_date = models.DateField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(principal__gt=0),
                name="loan_principal_positive",
            ),
            models.CheckConstraint(
                condition=Q(annual_rate__gte=0),
                name="loan_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(term_months__gte=1),
                name="loan_term_positive",
            ),
        ]

    def __str__(self):
        return f"Loan #{self.pk} ({self.client})"


# ==========================================
# 3. INSTALLMENTS / AMORTIZATION
# ==========================================

class Installment(models.Model):

    class Status(models.TextChoices):
        DUE = "due", "Due"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    loan = models.ForeignKey(
        Loan,
        on_delete=models.PROTECT,
        related_name="installments",
    )

    number = models.PositiveSmallIntegerField()
    due_date = models.DateField()

    principal_due = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    interest_due = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    penalty_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DUE,
    )

    class Meta:
        ordering = ["loan", "number"]

        constraints = [
            models.UniqueConstraint(
                fields=["loan", "number"],
                name="unique_installment_number",
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1),
                name="installment_number_positive",
            ),
            models.CheckConstraint(
                condition=Q(principal_due__gte=0),
                name="installment_principal_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(interest_due__gte=0),
                name="installment_interest_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0),
                name="installment_amount_paid_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(penalty_amount__gte=0),
                name="installment_penalty_nonnegative",
            ),
        ]

    @property
    def total_due(self):
        return (
            self.principal_due
            + self.interest_due
            + self.penalty_amount
        )


# ==========================================
# 4. LOAN ELIGIBILITY RULES
# ==========================================

class LoanRule(models.Model):

    product = models.OneToOneField(
        LoanProduct,
        on_delete=models.CASCADE,
        related_name="eligibility_rule",
    )

    minimum_monthly_income = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    minimum_credit_score = models.PositiveIntegerField(
        default=0,
    )

    minimum_age = models.PositiveSmallIntegerField(
        default=18,
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(minimum_monthly_income__gte=0),
                name="loan_rule_income_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(minimum_age__gte=18),
                name="loan_rule_min_age_18",
            ),
        ]

    def __str__(self):
        return f"Eligibility rules for {self.product.name}"


# ==========================================
# 5. ELIGIBILITY CHECK RESULTS
# ==========================================

class EligibilityCheck(models.Model):

    class Result(models.TextChoices):
        ELIGIBLE = "eligible", "Eligible"
        INELIGIBLE = "ineligible", "Ineligible"
        REVIEW = "review", "Needs Review"

    loan = models.ForeignKey(
        Loan,
        on_delete=models.PROTECT,
        related_name="eligibility_checks",
    )

    result = models.CharField(
        max_length=12,
        choices=Result.choices,
        default=Result.REVIEW,
    )

    remarks = models.TextField(blank=True)

    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="loan_eligibility_checks",
    )

    checked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Eligibility check for Loan #{self.loan_id}"


# ==========================================
# 6. LOAN AGREEMENTS
# ==========================================

class LoanAgreement(models.Model):

    loan = models.OneToOneField(
        Loan,
        on_delete=models.PROTECT,
        related_name="agreement",
    )

    agreement_number = models.CharField(
        max_length=40,
        unique=True,
    )

    agreement_date = models.DateField()

    # Records when the client accepts the agreement.
    # NULL means the agreement has not been accepted.
    signed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    terms_and_conditions = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.agreement_number


# ==========================================
# 7. LOAN PAYMENT RECORDS
# ==========================================

class LoanPayment(models.Model):

    loan = models.ForeignKey(
        Loan,
        on_delete=models.PROTECT,
        related_name="payment_records",
    )

    ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="loan_payment_record",
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    payment_date = models.DateTimeField(auto_now_add=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_loan_payments",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="loan_payment_amount_positive",
            ),
        ]

    def __str__(self):
        return f"Payment for Loan #{self.loan_id}"


# ==========================================
# 8. LOAN DISBURSEMENT RECORDS
# ==========================================

class Disbursement(models.Model):

    loan = models.OneToOneField(
        Loan,
        on_delete=models.PROTECT,
        related_name="disbursement_record",
    )

    savings_account = models.ForeignKey(
        "savings.SavingsAccount",
        on_delete=models.PROTECT,
        related_name="loan_disbursement_records",
    )

    ledger_entry = models.OneToOneField(
        "accounting.LedgerEntry",
        on_delete=models.PROTECT,
        related_name="loan_disbursement_record",
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    disbursed_at = models.DateTimeField(auto_now_add=True)

    disbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_disbursements",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="disbursement_amount_positive",
            ),
        ]

    def __str__(self):
        return f"Disbursement for Loan #{self.loan_id}"
