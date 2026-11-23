
import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.models import BankAccount
from accounting.money import BankError
from accounts.models import Role, User
from clients.models import Client
from loans import services as loan_services
from loans.models import EligibilityCheck, Installment, Loan, LoanProduct, LoanRule
from savings import services as savings


def make_user(name, role):
    return User.objects.create_user(
        name,
        password="x",
        role=Role.objects.get(name=role),
    )


def make_client(
    name,
    income="50000",
    score=700,
    status=Client.VerificationStatus.ACTIVE,
):
    user = make_user(name, Role.CLIENT)

    return Client.objects.create(
        user=user,
        id_number_encrypted=b"x",
        id_number_hash=f"hash-{name}",
        verification_status=status,
        date_of_birth=timezone.localdate() - timedelta(days=25 * 365),
        monthly_income=Decimal(income),
        credit_score=score,
    )


def make_bank_account(client):
    """Create the client's regular bank account."""
    while True:
        account_number = str(
            secrets.randbelow(9000000000) + 1000000000
        )

        if not BankAccount.objects.filter(
            account_number=account_number
        ).exists():
            break

    return BankAccount.objects.create(
        client=client,
        account_number=account_number,
        balance=Decimal("0.00"),
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

        LoanRule.objects.create(
            product=self.product,
            minimum_credit_score=600,
        )

    def borrower(
        self,
        name="alice",
        income="50000",
        score=700,
        savings_amount=None,
    ):
        client = make_client(
            name,
            income=income,
            score=score,
        )

        bank_account = make_bank_account(client)

        savings_account = savings.open_account(
            client,
            self.staff,
        )

        if savings_amount:
            savings.staff_cash_deposit(
                bank_account.pk,
                savings_amount,
                self.staff,
            )

            savings.transfer_to_savings(
                bank_account.pk,
                savings_account.pk,
                savings_amount,
                client.user,
                3,
            )

        return client, savings_account, bank_account

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

    # ---------- Eligibility results ----------

    def test_all_criteria_met_is_eligible(self):
        client, _, _ = self.borrower(
            savings_amount="5000",
        )

        loan = self.apply(client)

        self.assertEqual(
            self.latest_check(loan).result,
            EligibilityCheck.Result.ELIGIBLE,
        )

    def test_one_failed_criterion_needs_review(self):
        client, _, _ = self.borrower()

        loan = self.apply(client)
        check = self.latest_check(loan)

        self.assertEqual(
            check.result,
            EligibilityCheck.Result.REVIEW,
        )
        self.assertIn("Savings", check.remarks)

    def test_two_failed_criteria_is_not_eligible(self):
        client, _, _ = self.borrower(
            income="1000",
        )

        loan = self.apply(client)

        self.assertEqual(
            self.latest_check(loan).result,
            EligibilityCheck.Result.INELIGIBLE,
        )

    def test_credit_score_uses_the_product_rule(self):
        self.product.eligibility_rule.minimum_credit_score = 800
        self.product.eligibility_rule.save()

        client, _, _ = self.borrower(
            savings_amount="5000",
            score=700,
        )

        loan = self.apply(client)
        check = self.latest_check(loan)

        self.assertEqual(
            check.result,
            EligibilityCheck.Result.REVIEW,
        )
        self.assertIn("Credit score", check.remarks)

    # ---------- Loan officer permissions ----------

    def test_not_eligible_loan_cannot_be_approved(self):
        client, _, _ = self.borrower(
            income="1000",
        )

        loan = self.apply(client)

        with self.assertRaises(BankError):
            loan_services.approve_loan(
                loan.pk,
                self.officer,
            )

        loan.refresh_from_db()

        self.assertEqual(
            loan.status,
            Loan.Status.PENDING,
        )

    def test_needs_review_loan_can_be_approved_by_officer(self):
        client, _, _ = self.borrower()

        loan = self.apply(client)

        with self.assertRaises(BankError):
            loan_services.approve_loan(
                loan.pk,
                self.officer,
            )

        loan.refresh_from_db()

        self.assertEqual(
            loan.status,
            Loan.Status.PENDING,
        )


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

        return self.client.post(
            reverse("portal_apply"),
            {
                "product": self.product.pk,
                "principal": "12000",
                "term_months": "12",
                "purpose": "Personal and household expenses",
                "documents": SimpleUploadedFile("proof.pdf", b"%%PDF-1.4 test document", content_type="application/pdf"),
            },
        )

    def test_pending_client_cannot_apply(self):
        client = make_client(
            "pat",
            status=Client.VerificationStatus.PENDING,
        )

        self.post_application(client)

        self.assertEqual(
            Loan.objects.count(),
            0,
        )

    def test_rejected_client_cannot_apply(self):
        client = make_client(
            "rex",
            status=Client.VerificationStatus.REJECTED,
        )

        self.post_application(client)

        self.assertEqual(
            Loan.objects.count(),
            0,
        )

    def test_active_client_can_apply(self):
        client = make_client("amy")

        self.post_application(client)

        self.assertEqual(
            Loan.objects.filter(client=client).count(),
            1,
        )

    def test_client_with_overdue_installment_cannot_apply_again(self):
        client = make_client("olga")

        bank_account = make_bank_account(client)

        savings_account = savings.open_account(
            client,
            self.staff,
        )

        savings.staff_cash_deposit(
            bank_account.pk,
            "5000",
            self.staff,
        )

        savings.transfer_to_savings(
            bank_account.pk,
            savings_account.pk,
            "5000",
            client.user,
            3,
        )

        loan = loan_services.apply_for_loan(
            client,
            self.product,
            "12000",
            12,
            self.staff,
            purpose="Personal and household expenses",
        )

        loan_services.approve_loan(
            loan.pk,
            self.officer,
        )

        loan_services.create_loan_agreement(
            loan.pk,
            f"TEST-AGREEMENT-{loan.pk}",
            timezone.localdate(),
            "Test loan agreement terms and conditions.",
        )

        loan_services.accept_loan_agreement(
            loan.pk,
            client.user,
        )

        loan_services.disburse_loan(
            loan.pk,
            self.staff,
            bank_account.pk,
        )

        Installment.objects.filter(
            loan=loan,
            number=1,
        ).update(
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

        self.assertEqual(
            Loan.objects.filter(client=client).count(),
            1,
        )
