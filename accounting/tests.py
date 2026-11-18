from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase

from accounts.models import Role, User
from audit.models import AuditLog
from clients.models import Client
from loans.models import Installment, Loan, LoanProduct
from loans import services as loan_services
from savings import services as savings
from savings.models import SavingsAccount

from .models import LedgerEntry
from .money import BankError, to_money


def make_user(name, role):
    return User.objects.create_user(name, password="x", role=Role.objects.get(name=role))


def make_client(name):
    user = make_user(name, Role.CLIENT)
    # dummy encrypted value so these tests do not need FIELD_KEY
    return Client.objects.create(user=user, id_number_encrypted=b"x", id_number_hash=f"hash-{name}")


class MoneyInputTests(TestCase):
    def test_bad_amounts_are_rejected(self):
        for bad in ["0", "-5", "abc", "", None, "1.234", "NaN", "Infinity", "1e500", "9" * 20]:
            with self.assertRaises(BankError, msg=repr(bad)):
                to_money(bad)

    def test_good_amounts_are_accepted(self):
        self.assertEqual(to_money("10.50"), Decimal("10.50"))
        self.assertEqual(to_money(5), Decimal("5.00"))
        self.assertEqual(to_money(" 7 "), Decimal("7.00"))


class SavingsTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", Role.STAFF)
        self.client_a = make_client("alice")
        self.client_b = make_client("bob")
        self.a = savings.open_account(self.client_a, self.staff)
        self.b = savings.open_account(self.client_b, self.staff)

    def fresh(self, account):
        account.refresh_from_db()
        return account

    def test_deposit_and_withdraw(self):
        savings.deposit(self.a.pk, "100.00", self.staff)
        entry = savings.withdraw(self.a.pk, "40.25", self.staff)
        self.assertEqual(self.fresh(self.a).balance, Decimal("59.75"))
        self.assertEqual(entry.balance_after, Decimal("59.75"))

    def test_overdraw_is_blocked_and_changes_nothing(self):
        savings.deposit(self.a.pk, "50", self.staff)
        before = LedgerEntry.objects.count()
        with self.assertRaises(BankError):
            savings.withdraw(self.a.pk, "50.01", self.staff)
        self.assertEqual(self.fresh(self.a).balance, Decimal("50.00"))
        self.assertEqual(LedgerEntry.objects.count(), before)

    def test_transfer_moves_money_and_writes_two_entries(self):
        savings.deposit(self.a.pk, "100", self.staff)
        savings.transfer(self.a.pk, self.b.account_number, "30", self.staff)
        self.assertEqual(self.fresh(self.a).balance, Decimal("70.00"))
        self.assertEqual(self.fresh(self.b).balance, Decimal("30.00"))
        refs = LedgerEntry.objects.filter(reference__startswith="TRF-")
        self.assertEqual(refs.count(), 2)
        self.assertEqual(refs.values("reference").distinct().count(), 1)

    def test_transfer_failures_change_nothing(self):
        savings.deposit(self.a.pk, "10", self.staff)
        before = LedgerEntry.objects.count()
        with self.assertRaises(BankError):   # too much
            savings.transfer(self.a.pk, self.b.account_number, "10.01", self.staff)
        with self.assertRaises(BankError):   # same account
            savings.transfer(self.a.pk, self.a.account_number, "1", self.staff)
        with self.assertRaises(BankError):   # unknown destination
            savings.transfer(self.a.pk, "0000000000", "1", self.staff)
        self.b.status = SavingsAccount.Status.FROZEN
        self.b.save()
        with self.assertRaises(BankError):   # frozen destination
            savings.transfer(self.a.pk, self.b.account_number, "1", self.staff)
        self.assertEqual(self.fresh(self.a).balance, Decimal("10.00"))
        self.assertEqual(self.fresh(self.b).balance, Decimal("0.00"))
        self.assertEqual(LedgerEntry.objects.count(), before)

    def test_balance_always_equals_ledger_total(self):
        savings.deposit(self.a.pk, "200", self.staff)
        savings.withdraw(self.a.pk, "20.50", self.staff)
        savings.transfer(self.a.pk, self.b.account_number, "79.50", self.staff)
        savings.transfer(self.b.pk, self.a.account_number, "10", self.staff)
        plus = (LedgerEntry.EntryType.DEPOSIT, LedgerEntry.EntryType.TRANSFER_IN)
        for acct in (self.a, self.b):
            entries = LedgerEntry.objects.filter(savings_account=acct)
            total = (entries.filter(entry_type__in=plus).aggregate(s=Sum("amount"))["s"] or 0) - (
                entries.exclude(entry_type__in=plus).aggregate(s=Sum("amount"))["s"] or 0
            )
            self.assertEqual(self.fresh(acct).balance, total)

    def test_actions_are_audited(self):
        savings.deposit(self.a.pk, "5", self.staff)
        self.assertTrue(AuditLog.objects.filter(action="deposit", user=self.staff).exists())


class LoanTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", Role.STAFF)
        self.officer = make_user("officer1", Role.LOAN_OFFICER)
        self.client_a = make_client("alice")
        self.account = savings.open_account(self.client_a, self.staff)
        self.product = LoanProduct.objects.create(
            name="Personal", annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000"), max_amount=Decimal("50000"),
            min_months=3, max_months=24,
        )

    def apply(self, principal="12000", months=12):
        return loan_services.apply_for_loan(self.client_a, self.product, principal, months, self.staff)

    def active_loan(self):
        loan = self.apply()
        loan_services.approve_loan(loan.pk, self.officer)
        return loan_services.disburse_loan(loan.pk, self.officer, self.account.pk)

    def test_application_limits(self):
        for principal, months in [("999", 12), ("50001", 12), ("5000", 2), ("5000", 25)]:
            with self.assertRaises(BankError):
                self.apply(principal, months)
        self.product.is_active = False
        self.product.save()
        with self.assertRaises(BankError):
            self.apply()

    def test_only_deciders_can_approve(self):
        loan = self.apply()
        with self.assertRaises(BankError):
            loan_services.approve_loan(loan.pk, self.staff)
        loan_services.approve_loan(loan.pk, self.officer)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.APPROVED)
        self.assertEqual(loan.decided_by, self.officer)

    def test_cannot_approve_twice_or_own_loan(self):
        loan = self.apply()
        loan_services.approve_loan(loan.pk, self.officer)
        with self.assertRaises(BankError):
            loan_services.approve_loan(loan.pk, self.officer)
        own = Client.objects.create(user=self.officer, id_number_encrypted=b"x", id_number_hash="h-off")
        own_loan = loan_services.apply_for_loan(own, self.product, "2000", 6, self.officer)
        with self.assertRaises(BankError):
            loan_services.approve_loan(own_loan.pk, self.officer)

    def test_reject_needs_reason(self):
        loan = self.apply()
        with self.assertRaises(BankError):
            loan_services.reject_loan(loan.pk, self.officer, "  ")
        loan_services.reject_loan(loan.pk, self.officer, "Income too low")
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.REJECTED)

    def test_cannot_disburse_unapproved_or_to_wrong_account(self):
        loan = self.apply()
        with self.assertRaises(BankError):
            loan_services.disburse_loan(loan.pk, self.officer, self.account.pk)
        loan_services.approve_loan(loan.pk, self.officer)
        other = savings.open_account(make_client("bob"), self.staff)
        with self.assertRaises(BankError):
            loan_services.disburse_loan(loan.pk, self.officer, other.pk)

    def test_disburse_creates_schedule_and_credits_account(self):
        loan = self.active_loan()
        self.account.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.ACTIVE)
        self.assertEqual(self.account.balance, Decimal("12000.00"))
        items = list(loan.installments.all())
        self.assertEqual(len(items), 12)
        self.assertEqual(sum(i.principal_due for i in items), Decimal("12000.00"))
        self.assertTrue(LedgerEntry.objects.filter(
            loan=loan, entry_type=LedgerEntry.EntryType.LOAN_DISBURSEMENT).exists())

    def test_payments_fill_installments_in_order_then_close_loan(self):
        loan = self.active_loan()
        first = loan.installments.get(number=1)
        half = (first.total_due / 2).quantize(Decimal("0.01"))
        loan_services.record_payment(loan.pk, half, self.staff)
        first.refresh_from_db()
        self.assertEqual(first.status, Installment.Status.DUE)   # still partly unpaid
        loan_services.record_payment(loan.pk, first.total_due - half, self.staff)
        first.refresh_from_db()
        self.assertEqual(first.status, Installment.Status.PAID)
        self.assertEqual(loan.installments.get(number=2).amount_paid, Decimal("0"))

        remaining = sum(i.total_due - i.amount_paid for i in loan.installments.exclude(status="paid"))
        with self.assertRaises(BankError):   # overpay
            loan_services.record_payment(loan.pk, remaining + Decimal("0.01"), self.staff)
        loan_services.record_payment(loan.pk, remaining, self.staff)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.PAID)
        with self.assertRaises(BankError):   # nothing left to pay
            loan_services.record_payment(loan.pk, "1", self.staff)

    def test_only_staff_or_admin_record_payments(self):
        loan = self.active_loan()
        with self.assertRaises(BankError):
            loan_services.record_payment(loan.pk, "10", self.officer)