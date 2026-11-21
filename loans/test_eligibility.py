
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.money import BankError
from accounts.models import Role, User
from clients.models import Client
from loans import services as loan_services
from loans.models import EligibilityCheck, Installment, Loan, LoanProduct, LoanRule
from savings import services as savings


def make_user(name, role):
    return User.objects.create_user(name, password="x", role=Role.objects.get(name=role))


def make_client(name, income="50000", score=700, status=Client.VerificationStatus.ACTIVE):
    user = make_user(name, Role.CLIENT)
    return Client.objects.create(
        user=user,
        id_number_encrypted=b"x",
        id_number_hash=f"hash-{name}",
        verification_status=status,
        monthly_income=Decimal(income),
        credit_score=score,
    )


class EligibilityTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", Role.STAFF)
        self.officer = make_user("officer1", Role.LOAN_OFFICER)
        self.product = LoanProduct.objects.create(
            name="Personal",
            annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000"),
            max_amount=Decimal("50000"),
            min_months=3,
            max_months=24,
        )
        # Defaults: installment <= 40% of income, savings >= 10% of the loan.
        LoanRule.objects.create(product=self.product, minimum_credit_score=600)

    def borrower(self, name="alice", income="50000", score=700, savings_amount=None):
        client = make_client(name, income=income, score=score)
        account = savings.open_account(client, self.staff)
        if savings_amount:
            savings.deposit(account.pk, savings_amount, self.staff)
        return client, account

    def apply(self, client, principal="12000", months=12):
        return loan_services.apply_for_loan(
            client,
            self.product,
            principal,
            months,
            self.staff,
            purpose="Personal and household expenses",
        )

    def latest_check(self, loan):
        return loan.eligibility_checks.order_by("-pk").first()

    # ---------- the three results ----------

    def test_all_criteria_met_is_eligible(self):
        client, _ = self.borrower(savings_amount="5000")
        loan = self.apply(client)
        self.assertEqual(self.latest_check(loan).result, EligibilityCheck.Result.ELIGIBLE)

    def test_one_failed_criterion_needs_review(self):
        client, _ = self.borrower()  # no savings
        loan = self.apply(client)
        check = self.latest_check(loan)
        self.assertEqual(check.result, EligibilityCheck.Result.REVIEW)
        self.assertIn("Savings", check.remarks)

    def test_two_failed_criteria_is_not_eligible(self):
        client, _ = self.borrower(income="1000")  # low income and no savings
        loan = self.apply(client)
        self.assertEqual(self.latest_check(loan).result, EligibilityCheck.Result.INELIGIBLE)

    def test_credit_score_uses_the_product_rule(self):
        self.product.eligibility_rule.minimum_credit_score = 800
        self.product.eligibility_rule.save()
        client, _ = self.borrower(savings_amount="5000", score=700)
        loan = self.apply(client)
        check = self.latest_check(loan)
        self.assertEqual(check.result, EligibilityCheck.Result.REVIEW)
        self.assertIn("Credit score", check.remarks)

    # ---------- what the officer can do ----------

    def test_not_eligible_loan_cannot_be_approved(self):
        client, _ = self.borrower(income="1000")
        loan = self.apply(client)
        with self.assertRaises(BankError):
            loan_services.approve_loan(loan.pk, self.officer)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.PENDING)

    def test_needs_review_loan_can_be_approved_by_officer(self):
        client, _ = self.borrower()  # one failed criterion
        loan = self.apply(client)
        loan_services.approve_loan(loan.pk, self.officer)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.APPROVED)


class LoanApplicationRuleTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", Role.STAFF)
        self.officer = make_user("officer1", Role.LOAN_OFFICER)
        self.product = LoanProduct.objects.create(
            name="Personal",
            annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000"),
            max_amount=Decimal("50000"),
            min_months=3,
            max_months=24,
        )

    def post_application(self, client):
        self.client.force_login(client.user)
        return self.client.post(reverse("portal_apply"), {
            "product": self.product.pk,
            "principal": "12000",
            "term_months": "12",
            "purpose": "Personal and household expenses",
        })

    def test_pending_client_cannot_apply(self):
        client = make_client("pat", status=Client.VerificationStatus.PENDING)
        self.post_application(client)
        self.assertEqual(Loan.objects.count(), 0)

    def test_rejected_client_cannot_apply(self):
        client = make_client("rex", status=Client.VerificationStatus.REJECTED)
        self.post_application(client)
        self.assertEqual(Loan.objects.count(), 0)

    def test_active_client_can_apply(self):
        client = make_client("amy")
        self.post_application(client)
        self.assertEqual(Loan.objects.filter(client=client).count(), 1)

    def test_client_with_overdue_installment_cannot_apply_again(self):
        client = make_client("olga")
        account = savings.open_account(client, self.staff)
        savings.deposit(account.pk, "5000", self.staff)

        loan = loan_services.apply_for_loan(
            client,
            self.product,
            "12000",
            12,
            self.staff,
            purpose="Personal and household expenses",
        )
        loan_services.approve_loan(loan.pk, self.officer)
        loan_services.disburse_loan(loan.pk, self.officer, account.pk)

        Installment.objects.filter(loan=loan, number=1).update(
            due_date=timezone.localdate() - timedelta(days=5)
        )

        with self.assertRaises(BankError):
            loan_services.apply_for_loan(
                client,
                self.product,
                "5000",
                6,
                self.staff,
                purpose="Emergency expenses",
            )

        self.assertEqual(Loan.objects.filter(client=client).count(), 1)
