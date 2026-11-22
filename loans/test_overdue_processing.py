
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role
from clients.models import Client as BankClient
from loans.models import Installment, Loan, LoanProduct
from notifications.models import Notification


class OverdueProcessingTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        client_role, _ = Role.objects.get_or_create(
            name=Role.CLIENT
        )

        cls.user = User.objects.create_user(
            username="overdue_test_client",
            password="TestPassword123!",
            role=client_role,
        )

        cls.bank_client = BankClient(
            user=cls.user,
            verification_status=BankClient.VerificationStatus.ACTIVE,
        )
        cls.bank_client.set_id_number("OVERDUE-TEST-ID-001")
        cls.bank_client.save()

        cls.product = LoanProduct.objects.create(
            name="Overdue Test Loan",
            annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000.00"),
            max_amount=Decimal("100000.00"),
            min_months=1,
            max_months=12,
        )

    def setUp(self):
        self.loan = Loan.objects.create(
            client=self.bank_client,
            product=self.product,
            principal=Decimal("10000.00"),
            annual_rate=Decimal("12.00"),
            term_months=1,
            status=Loan.Status.ACTIVE,
        )

        self.installment = Installment.objects.create(
            loan=self.loan,
            number=1,
            due_date=timezone.localdate() - timedelta(days=5),
            principal_due=Decimal("1000.00"),
            interest_due=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            penalty_amount=Decimal("0.00"),
            status=Installment.Status.DUE,
        )

    def run_overdue_command(self):
        output = StringIO()

        call_command(
            "process_overdue_loans",
            stdout=output,
        )

        return output.getvalue()

    def test_marks_installment_overdue(self):
        self.run_overdue_command()
        self.installment.refresh_from_db()

        self.assertEqual(
            self.installment.status,
            Installment.Status.OVERDUE,
        )

    def test_applies_two_percent_penalty(self):
        self.run_overdue_command()
        self.installment.refresh_from_db()

        self.assertEqual(
            self.installment.penalty_amount,
            Decimal("22.00"),
        )

    def test_penalty_is_not_applied_twice(self):
        self.run_overdue_command()
        self.run_overdue_command()
        self.installment.refresh_from_db()

        self.assertEqual(
            self.installment.penalty_amount,
            Decimal("22.00"),
        )

    def test_creates_overdue_notification(self):
        self.run_overdue_command()

        self.assertTrue(
            Notification.objects.filter(
                user=self.user,
                kind="loan_overdue",
            ).exists()
        )

    def test_notification_is_not_duplicated(self):
        self.run_overdue_command()
        self.run_overdue_command()

        self.assertEqual(
            Notification.objects.filter(
                user=self.user,
                kind="loan_overdue",
            ).count(),
            1,
        )

    def test_paid_installment_is_not_penalized(self):
        self.installment.status = Installment.Status.PAID
        self.installment.amount_paid = Decimal("1100.00")
        self.installment.save(
            update_fields=["status", "amount_paid"]
        )

        self.run_overdue_command()
        self.installment.refresh_from_db()

        self.assertEqual(
            self.installment.penalty_amount,
            Decimal("0.00"),
        )

        self.assertEqual(
            self.installment.status,
            Installment.Status.PAID,
        )

    def test_fully_paid_loan_is_marked_paid(self):
        self.installment.amount_paid = Decimal("1100.00")
        self.installment.save(
            update_fields=["amount_paid"]
        )

        self.run_overdue_command()
        self.loan.refresh_from_db()

        self.assertEqual(
            self.loan.status,
            Loan.Status.PAID,
        )
