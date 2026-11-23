from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Role
from accounting.models import LedgerEntry
from clients.models import Client as BankClient
from notifications.models import Notification
from savings.interest import (
    calculate_monthly_interest,
    post_monthly_interest,
)
from savings.models import SavingsAccount, SavingsInterestPosting


@override_settings(FIELD_KEY=Fernet.generate_key().decode())
class SavingsInterestTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        admin_role, _ = Role.objects.get_or_create(
            name=Role.ADMIN
        )
        client_role, _ = Role.objects.get_or_create(
            name=Role.CLIENT
        )

        cls.admin_user = User.objects.create_user(
            username="interest_test_admin",
            password="TestPassword123!",
            role=admin_role,
        )

        cls.borrower_user = User.objects.create_user(
            username="interest_test_client",
            password="TestPassword123!",
            role=client_role,
        )

        cls.bank_client = BankClient(
            user=cls.borrower_user,
            verification_status=BankClient.VerificationStatus.ACTIVE,
        )
        cls.bank_client.set_id_number("INTEREST-TEST-ID-001")
        cls.bank_client.save()

    def setUp(self):
        self.account = SavingsAccount.objects.create(
            client=self.bank_client,
            account_number="SAV-INTEREST-001",
            balance=Decimal("12000.00"),
            status=SavingsAccount.Status.ACTIVE,
        )

        previous_month = (
            timezone.localdate().replace(day=1)
            - timedelta(days=1)
        )
        self.year = previous_month.year
        self.month = previous_month.month

    def post_interest(self):
        return post_monthly_interest(
            year=self.year,
            month=self.month,
            by=self.admin_user,
        )

    def test_monthly_interest_calculation(self):
        result = calculate_monthly_interest(
            Decimal("12000.00")
        )
        self.assertEqual(result, Decimal("20.00"))

    def test_interest_increases_savings_balance(self):
        result = self.post_interest()
        self.account.refresh_from_db()

        self.assertEqual(
            self.account.balance,
            Decimal("12020.00"),
        )
        self.assertEqual(result["posted"], 1)

    def test_creates_interest_ledger_entry(self):
        self.post_interest()

        entry = LedgerEntry.objects.get(
            savings_account=self.account,
            entry_type=LedgerEntry.EntryType.INTEREST_CREDIT,
        )

        self.assertEqual(entry.amount, Decimal("20.00"))
        self.assertEqual(
            entry.balance_after,
            Decimal("12020.00"),
        )
        self.assertEqual(entry.created_by, self.admin_user)

    def test_creates_monthly_posting_record(self):
        self.post_interest()

        posting = SavingsInterestPosting.objects.get(
            savings_account=self.account,
            year=self.year,
            month=self.month,
        )

        self.assertEqual(posting.amount, Decimal("20.00"))
        self.assertEqual(posting.posted_by, self.admin_user)
        self.assertEqual(
            posting.ledger_entry.entry_type,
            LedgerEntry.EntryType.INTEREST_CREDIT,
        )

    def test_prevents_duplicate_monthly_posting(self):
        self.post_interest()
        result = self.post_interest()
        self.account.refresh_from_db()

        self.assertEqual(result["posted"], 0)
        self.assertEqual(
            self.account.balance,
            Decimal("12020.00"),
        )
        self.assertEqual(
            SavingsInterestPosting.objects.filter(
                savings_account=self.account,
                year=self.year,
                month=self.month,
            ).count(),
            1,
        )

    def test_frozen_account_is_skipped(self):
        self.account.status = SavingsAccount.Status.FROZEN
        self.account.save(update_fields=["status"])

        result = self.post_interest()
        self.account.refresh_from_db()

        self.assertEqual(result["posted"], 0)
        self.assertEqual(
            self.account.balance,
            Decimal("12000.00"),
        )

    def test_zero_balance_is_skipped(self):
        self.account.balance = Decimal("0.00")
        self.account.save(update_fields=["balance"])

        result = self.post_interest()

        self.assertEqual(result["posted"], 0)
        self.assertFalse(
            SavingsInterestPosting.objects.filter(
                savings_account=self.account
            ).exists()
        )

    def test_creates_interest_notification(self):
        self.post_interest()

        self.assertTrue(
            Notification.objects.filter(
                user=self.borrower_user,
                kind="savings_interest",
            ).exists()
        )

    def test_future_month_is_rejected(self):
        today = timezone.localdate()

        with self.assertRaises(ValueError):
            post_monthly_interest(
                year=today.year,
                month=today.month,
                by=self.admin_user,
            )

    def test_management_command_posts_interest(self):
        call_command(
            "post_savings_interest",
            year=self.year,
            month=self.month,
            by=self.admin_user.username,
            verbosity=0,
        )

        self.account.refresh_from_db()

        self.assertEqual(
            self.account.balance,
            Decimal("12020.00"),
        )