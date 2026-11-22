
from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User
from clients.models import Client

from accounting.client_services import client_bank_transfer
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError


class ClientBankTransferTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        role, _ = Role.objects.get_or_create(
            name=Role.CLIENT
        )

        cls.alice_user = User.objects.create_user(
            "transfer_alice",
            password="test-only-password",
            role=role,
        )

        cls.bob_user = User.objects.create_user(
            "transfer_bob",
            password="test-only-password",
            role=role,
        )

        cls.alice = Client.objects.create(
            user=cls.alice_user,
            id_number_encrypted=b"test-alice",
            id_number_hash="transfer-test-alice",
        )

        cls.bob = Client.objects.create(
            user=cls.bob_user,
            id_number_encrypted=b"test-bob",
            id_number_hash="transfer-test-bob",
        )

        cls.alice_account = BankAccount.objects.create(
            client=cls.alice,
            account_number="BA-TEST-ALICE",
            balance=Decimal("1000.00"),
            status=BankAccount.Status.ACTIVE,
        )

        cls.bob_account = BankAccount.objects.create(
            client=cls.bob,
            account_number="BA-TEST-BOB",
            balance=Decimal("500.00"),
            status=BankAccount.Status.ACTIVE,
        )

    def assert_balances(self, alice, bob):
        self.alice_account.refresh_from_db()
        self.bob_account.refresh_from_db()

        self.assertEqual(
            self.alice_account.balance,
            Decimal(alice),
        )
        self.assertEqual(
            self.bob_account.balance,
            Decimal(bob),
        )

    def test_successful_transfer(self):
        outgoing, incoming = client_bank_transfer(
            self.alice_account.pk,
            self.bob_account.account_number,
            "200.00",
            self.alice_user,
        )

        self.assert_balances("800.00", "700.00")

        self.assertEqual(
            outgoing.entry_type,
            LedgerEntry.EntryType.TRANSFER_OUT,
        )

        self.assertEqual(
            incoming.entry_type,
            LedgerEntry.EntryType.TRANSFER_IN,
        )

        self.assertEqual(
            outgoing.reference,
            incoming.reference,
        )

        self.assertEqual(
            LedgerEntry.objects.count(),
            2,
        )

    def test_cannot_transfer_from_another_client(self):
        before = LedgerEntry.objects.count()

        with self.assertRaises(BankError):
            client_bank_transfer(
                self.bob_account.pk,
                self.alice_account.account_number,
                "100.00",
                self.alice_user,
            )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(
            LedgerEntry.objects.count(),
            before,
        )

    def test_insufficient_balance(self):
        with self.assertRaises(BankError):
            client_bank_transfer(
                self.alice_account.pk,
                self.bob_account.account_number,
                "1000.01",
                self.alice_user,
            )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_cannot_transfer_to_same_account(self):
        with self.assertRaises(BankError):
            client_bank_transfer(
                self.alice_account.pk,
                self.alice_account.account_number,
                "100.00",
                self.alice_user,
            )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_cannot_transfer_to_frozen_account(self):
        self.bob_account.status = BankAccount.Status.FROZEN
        self.bob_account.save(update_fields=["status"])

        with self.assertRaises(BankError):
            client_bank_transfer(
                self.alice_account.pk,
                self.bob_account.account_number,
                "100.00",
                self.alice_user,
            )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_cannot_transfer_from_frozen_account(self):
        self.alice_account.status = BankAccount.Status.FROZEN
        self.alice_account.save(update_fields=["status"])

        with self.assertRaises(BankError):
            client_bank_transfer(
                self.alice_account.pk,
                self.bob_account.account_number,
                "100.00",
                self.alice_user,
            )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_invalid_amount_is_rejected(self):
        for amount in ("0", "-100", "abc", "1.234"):
            with self.subTest(amount=amount):
                with self.assertRaises(BankError):
                    client_bank_transfer(
                        self.alice_account.pk,
                        self.bob_account.account_number,
                        amount,
                        self.alice_user,
                    )

        self.assert_balances("1000.00", "500.00")
        self.assertEqual(LedgerEntry.objects.count(), 0)
