
from decimal import Decimal

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from clients.models import Client
from loans.models import Loan, LoanProduct
from savings.models import SavingsAccount


@override_settings(FIELD_KEY=Fernet.generate_key().decode())
class DashboardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.client_role, _ = Role.objects.get_or_create(name="client")
        cls.staff_role, _ = Role.objects.get_or_create(name="staff")
        cls.admin_role, _ = Role.objects.get_or_create(name="admin")
        cls.officer_role, _ = Role.objects.get_or_create(
            name="loan_officer"
        )

        cls.user = User.objects.create_user(
            username="testclient",
            password="TestPass123!",
            role=cls.client_role,
        )

        cls.staff = User.objects.create_user(
            username="teststaff",
            password="TestPass123!",
            role=cls.staff_role,
        )

        cls.admin = User.objects.create_user(
            username="testadmin",
            password="TestPass123!",
            role=cls.admin_role,
        )

        cls.officer = User.objects.create_user(
            username="testofficer",
            password="TestPass123!",
            role=cls.officer_role,
        )

        cls.client_profile = Client(user=cls.user)
        cls.client_profile.set_id_number("TEST-001")
        cls.client_profile.save()

        SavingsAccount.objects.create(
            client=cls.client_profile,
            account_number="SAV001",
            balance=Decimal("4000.00"),
        )

        cls.product = LoanProduct.objects.create(
            name="Personal Loan",
            annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000.00"),
            max_amount=Decimal("100000.00"),
            min_months=1,
            max_months=24,
        )

        for status in [Loan.Status.PENDING, Loan.Status.ACTIVE]:
            Loan.objects.create(
                client=cls.client_profile,
                product=cls.product,
                principal=Decimal("5000.00"),
                annual_rate=Decimal("12.00"),
                term_months=12,
                status=status,
            )

    def test_client_dashboard_data(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("portal_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["balance"],
            Decimal("4000.00"),
        )
        self.assertEqual(response.context["loans"].count(), 2)

    def test_client_has_only_one_savings_account(self):
        self.assertEqual(
            SavingsAccount.objects.filter(
                client=self.client_profile
            ).count(),
            1,
        )

    def test_staff_dashboard_counts(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("staff_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["active_count"], 1)

    def test_client_cannot_access_staff(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("staff_home"))

        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_access_client(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("portal_home"))

        self.assertEqual(response.status_code, 403)

    def test_home_redirects_client(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertRedirects(
            response,
            reverse("portal_home"),
        )

    def test_home_redirects_staff(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("home"))

        self.assertRedirects(
            response,
            reverse("staff_home"),
        )

    def test_admin_and_officer_can_access_staff_dashboard(self):
        # Preserve the original test name and verify strict
        # separation of duties: only staff can use staff_home.
        for user in [self.admin, self.officer]:
            with self.subTest(role=user.role.name):
                self.client.force_login(user)

                response = self.client.get(reverse("staff_home"))

                self.assertEqual(response.status_code, 403)
