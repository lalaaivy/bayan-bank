
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import Role
from clients.models import Client


@override_settings(FIELD_KEY=Fernet.generate_key().decode())
class ClientModelTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.role, _ = Role.objects.get_or_create(name="client")

        self.user = User.objects.create_user(
            username="clienttest",
            password="TestPass123!",
            role=self.role,
        )

        self.client_profile = Client(user=self.user)
        self.client_profile.set_id_number("TEST-ID-12345")
        self.client_profile.save()

    def test_client_is_created(self):
        self.assertTrue(
            Client.objects.filter(pk=self.client_profile.pk).exists()
        )

    def test_id_number_can_be_decrypted(self):
        self.assertEqual(
            self.client_profile.get_id_number(),
            "TEST-ID-12345",
        )

    def test_id_number_is_stored_as_hash(self):
        self.assertTrue(self.client_profile.id_number_hash)
        self.assertNotEqual(
            self.client_profile.id_number_hash,
            "TEST-ID-12345",
        )

    def test_client_can_be_found_by_id_number(self):
        result = Client.find_by_id_number("TEST-ID-12345")

        self.assertEqual(result, self.client_profile)

    def test_client_code_format(self):
        self.assertEqual(
            self.client_profile.client_code,
            f"CLT-{self.client_profile.pk:06d}",
        )

    def test_client_string_representation(self):
        self.assertEqual(
            str(self.client_profile),
            "clienttest",
        )
