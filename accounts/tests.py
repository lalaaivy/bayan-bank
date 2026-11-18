
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse
from cryptography.fernet import Fernet
from django.test import override_settings

from accounts.models import Role
from accounts.views import home, portal_home, staff_home
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
        cls.officer_role, _ = Role.objects.get_or_create(name="loan_officer")

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

        cls.client_profile = Client(
            user=cls.user,
        )
        cls.client_profile.set_id_number("TEST-001")
        cls.client_profile.save()

        SavingsAccount.objects.create(
            client=cls.client_profile,
            account_number="SAV001",
            balance=Decimal("1500.00"),
        )

        SavingsAccount.objects.create(
            client=cls.client_profile,
            account_number="SAV002",
            balance=Decimal("2500.00"),
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

    def setUp(self):
        self.factory = RequestFactory()

    
    def test_client_dashboard_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("portal_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["balance"], Decimal("4000.00"))
        self.assertEqual(response.context["loans"].count(), 2)

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
        request = self.factory.get(reverse("home"))
        request.user = self.user

        response = home(request)

        self.assertEqual(response.url, reverse("portal_home"))

    def test_home_redirects_staff(self):
        request = self.factory.get(reverse("home"))
        request.user = self.staff

        response = home(request)

        self.assertEqual(response.url, reverse("staff_home"))

    def test_admin_and_officer_access(self):
        for user in [self.admin, self.officer]:
            request = self.factory.get(reverse("staff_home"))
            request.user = user

            response = staff_home(request)

            self.assertEqual(response.status_code, 200)
