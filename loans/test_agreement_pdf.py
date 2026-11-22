
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from clients.models import Client as BankClient
from loans.agreement_pdf import generate_agreement_pdf
from loans.models import Loan, LoanAgreement, LoanProduct


class LoanAgreementPDFTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        client_role, _ = Role.objects.get_or_create(
            name=Role.CLIENT
        )
        staff_role, _ = Role.objects.get_or_create(
            name="staff"
        )

        cls.borrower_user = User.objects.create_user(
            username="pdf_test_borrower",
            password="TestPassword123!",
            role=client_role,
        )

        cls.other_user = User.objects.create_user(
            username="pdf_test_other",
            password="TestPassword123!",
            role=client_role,
        )

        cls.staff_user = User.objects.create_user(
            username="pdf_test_staff",
            password="TestPassword123!",
            role=staff_role,
        )

        cls.borrower = BankClient(
            user=cls.borrower_user,
            verification_status=BankClient.VerificationStatus.ACTIVE,
        )
        cls.borrower.set_id_number("PDF-TEST-ID-001")
        cls.borrower.save()

        cls.other_client = BankClient(
            user=cls.other_user,
            verification_status=BankClient.VerificationStatus.ACTIVE,
        )
        cls.other_client.set_id_number("PDF-TEST-ID-002")
        cls.other_client.save()

        cls.product = LoanProduct.objects.create(
            name="PDF Test Loan",
            annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000.00"),
            max_amount=Decimal("100000.00"),
            min_months=1,
            max_months=12,
        )

        cls.loan = Loan.objects.create(
            client=cls.borrower,
            product=cls.product,
            principal=Decimal("10000.00"),
            annual_rate=Decimal("12.00"),
            term_months=12,
            status=Loan.Status.APPROVED,
        )

        cls.agreement = LoanAgreement.objects.create(
            loan=cls.loan,
            agreement_number="AGR-PDF-TEST-001",
            agreement_date=date.today(),
            terms_and_conditions=(
                "The borrower agrees to repay the loan "
                "according to the approved payment schedule."
            ),
        )

        cls.pdf_url = reverse(
            "loan_agreement_pdf",
            kwargs={"loan_id": cls.loan.pk},
        )

    def test_generates_valid_pdf(self):
        pdf_bytes = generate_agreement_pdf(
            self.loan,
            self.agreement,
        )

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 100)

    def test_loan_owner_can_download_pdf(self):
        self.client.force_login(self.borrower_user)

        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/pdf",
        )
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_staff_can_download_pdf(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_other_client_cannot_download_pdf(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cannot_download_pdf(self):
        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 403)

    def test_missing_agreement_returns_404(self):
        self.client.force_login(self.borrower_user)

        self.agreement.delete()

        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 404)
