
"""Bayan Bank accounting tests for current regular-bank, term-savings, and loan rules.

Preserves the 20 original test method names, with updated workflow assertions.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError, to_money
from audit.models import AuditLog
from clients.models import Client
from loans import services as loan_services
from loans.models import Installment, Loan, LoanProduct
from savings import services as savings
from savings.models import SavingsAccount, SavingsDeposit, SavingsInterestPosting


def make_user(name, role):
    return User.objects.create_user(
        name, password="x", role=Role.objects.get(name=role)
    )


def make_client(name):
    user = make_user(name, Role.CLIENT)
    return Client.objects.create(
        user=user,
        id_number_encrypted=b"x",
        id_number_hash=f"hash-{name}",
        verification_status=Client.VerificationStatus.ACTIVE,
        date_of_birth=timezone.localdate() - timedelta(days=25 * 365),
        monthly_income=Decimal("50000.00"),
        credit_score=700,
    )


def make_bank_account(client, suffix):
    return BankAccount.objects.create(
        client=client, account_number=f"BANK-TEST-{suffix}"
    )


class MoneyInputTests(TestCase):
    def test_bad_amounts_are_rejected(self):
        for bad in [
            "0", "-5", "abc", "", None, "1.234", "NaN",
            "Infinity", "1e500", "9" * 20,
        ]:
            with self.subTest(bad=bad), self.assertRaises(BankError):
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
        self.bank_a = make_bank_account(self.client_a, "A")
        self.bank_b = make_bank_account(self.client_b, "B")

    def fresh(self, account):
        account.refresh_from_db()
        return account

    def fund(self, amount="100.00"):
        return savings.staff_cash_deposit(self.bank_a.pk, amount, self.staff)

    def transfer(self, amount="40.00", months=3):
        return savings.transfer_to_savings(
            self.bank_a.pk, self.a.pk, amount,
            self.client_a.user, term_months=months,
        )

    def test_deposit_and_withdraw(self):
        entry = self.fund("100.00")
        self.assertEqual(self.fresh(self.bank_a).balance, Decimal("100.00"))
        self.assertEqual(entry.balance_after, Decimal("100.00"))
        self.assertEqual(self.fresh(self.a).balance, Decimal("0.00"))
        with self.assertRaises(BankError):
            savings.withdraw(self.a.pk, "40.25", self.staff)
        self.assertEqual(self.fresh(self.bank_a).balance, Decimal("100.00"))

    def test_overdraw_is_blocked_and_changes_nothing(self):
        self.fund("50")
        before = LedgerEntry.objects.count()
        with self.assertRaises(BankError):
            self.transfer("50.01")
        self.assertEqual(self.fresh(self.bank_a).balance, Decimal("50.00"))
        self.assertEqual(self.fresh(self.a).balance, Decimal("0.00"))
        self.assertEqual(LedgerEntry.objects.count(), before)

    def test_transfer_moves_money_and_writes_two_entries(self):
        self.fund("100")
        result = self.transfer("30")
        self.assertEqual(self.fresh(self.bank_a).balance, Decimal("70.00"))
        self.assertEqual(self.fresh(self.a).balance, Decimal("30.00"))
        self.assertEqual(result["bank_entry"].reference, result["savings_entry"].reference)
        refs = LedgerEntry.objects.filter(reference=result["reference"])
        self.assertEqual(refs.count(), 2)
        self.assertEqual(refs.values("reference").distinct().count(), 1)
        deposit = result["deposit"]
        self.assertEqual(deposit.amount, Decimal("30.00"))
        self.assertEqual(deposit.status, SavingsDeposit.Status.LOCKED)

    def test_transfer_failures_change_nothing(self):
        self.fund("10")
        before = LedgerEntry.objects.count()
        with self.assertRaises(BankError):
            self.transfer("10.01")
        with self.assertRaises(BankError):
            savings.transfer_to_savings(
                self.bank_a.pk, self.b.pk, "1", self.client_a.user,
                term_months=3,
            )
        with self.assertRaises(BankError):
            savings.transfer_to_savings(
                self.bank_a.pk, self.a.pk, "1", self.client_b.user,
                term_months=3,
            )
        self.b.status = SavingsAccount.Status.FROZEN
        self.b.save(update_fields=["status"])
        with self.assertRaises(BankError):
            savings.transfer_to_savings(
                self.bank_b.pk, self.b.pk, "1", self.client_b.user,
                term_months=3,
            )
        self.assertEqual(self.fresh(self.bank_a).balance, Decimal("10.00"))
        self.assertEqual(self.fresh(self.a).balance, Decimal("0.00"))
        self.assertEqual(self.fresh(self.b).balance, Decimal("0.00"))
        self.assertEqual(LedgerEntry.objects.count(), before)

    def test_monthly_interest_is_calculated_and_credited(self):
        self.fund("12000")
        result = self.transfer("12000", 3)
        deposit = result["deposit"]
        self.assertEqual(deposit.annual_rate, Decimal("2.00"))
        self.assertEqual(deposit.amount, Decimal("12000.00"))
        self.assertEqual(self.fresh(self.a).balance, Decimal("12000.00"))
        # Locked term principal is excluded from regular monthly interest.
        from savings.interest import get_regular_savings_balance, calculate_monthly_interest
        self.assertEqual(get_regular_savings_balance(self.a), Decimal("0.00"))
        self.assertEqual(calculate_monthly_interest(Decimal("12000")), Decimal("20.00"))
        self.assertFalse(SavingsInterestPosting.objects.filter(savings_account=self.a).exists())

    def test_interest_cannot_be_posted_twice_for_same_month(self):
        self.fund("12000")
        self.transfer("12000")
        before_balance = self.fresh(self.a).balance
        before_entries = LedgerEntry.objects.count()
        for _ in range(2):
            with self.assertRaises(BankError):
                savings.post_monthly_interest(self.a.pk, self.staff, year=2026, month=11)
        self.assertEqual(self.fresh(self.a).balance, before_balance)
        self.assertEqual(LedgerEntry.objects.count(), before_entries)
        self.assertFalse(SavingsInterestPosting.objects.filter(savings_account=self.a).exists())

    def test_frozen_account_cannot_receive_interest(self):
        self.fund("12000")
        self.transfer("12000")
        self.a.status = SavingsAccount.Status.FROZEN
        self.a.save(update_fields=["status"])
        before_balance = self.fresh(self.a).balance
        before_entries = LedgerEntry.objects.count()
        with self.assertRaises(BankError):
            savings.post_monthly_interest(self.a.pk, self.staff, year=2026, month=11)
        with self.assertRaises(BankError):
            self.transfer("1")
        self.assertEqual(self.fresh(self.a).balance, before_balance)
        self.assertEqual(LedgerEntry.objects.count(), before_entries)

    def test_empty_account_cannot_receive_interest(self):
        with self.assertRaises(BankError):
            savings.post_monthly_interest(self.a.pk, self.staff, year=2026, month=11)
        self.assertEqual(self.fresh(self.a).balance, Decimal("0.00"))

    def test_balance_always_equals_ledger_total(self):
        self.fund("200")
        self.transfer("80")
        plus = (
            LedgerEntry.EntryType.DEPOSIT,
            LedgerEntry.EntryType.TRANSFER_IN,
            LedgerEntry.EntryType.INTEREST_CREDIT,
            LedgerEntry.EntryType.LOAN_DISBURSEMENT,
        )
        for account in (self.bank_a, self.a, self.bank_b, self.b):
            lookup = (
                {"bank_account": account}
                if isinstance(account, BankAccount)
                else {"savings_account": account}
            )
            entries = LedgerEntry.objects.filter(**lookup)
            credits = entries.filter(entry_type__in=plus).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            debits = entries.exclude(entry_type__in=plus).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
            self.assertEqual(self.fresh(account).balance, credits - debits)

    def test_actions_are_audited(self):
        self.fund("5")
        self.transfer("3")
        self.assertTrue(AuditLog.objects.filter(action="staff_cash_deposit", user=self.staff).exists())
        self.assertTrue(AuditLog.objects.filter(action="bank_to_savings_transfer", user=self.client_a.user).exists())


class LoanTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff1", Role.STAFF)
        self.officer = make_user("officer1", Role.LOAN_OFFICER)
        self.client_a = make_client("alice")
        self.account = savings.open_account(self.client_a, self.staff)
        self.bank = make_bank_account(self.client_a, "LOAN")
        self.product = LoanProduct.objects.create(
            name="Personal", annual_rate=Decimal("12.00"),
            min_amount=Decimal("1000"), max_amount=Decimal("50000"),
            min_months=3, max_months=24,
        )

    def fund_savings(self):
        savings.staff_cash_deposit(self.bank.pk, "5000", self.staff)
        savings.transfer_to_savings(
            self.bank.pk, self.account.pk, "2000", self.client_a.user,
            term_months=3,
        )

    def apply(self, principal="12000", months=12):
        return loan_services.apply_for_loan(
            self.client_a, self.product, principal, months, self.staff,
            purpose="Personal and household expenses",
        )

    def approved(self):
        self.fund_savings()
        loan = self.apply()
        loan_services.approve_loan(loan.pk, self.officer)
        loan.refresh_from_db()
        return loan

    def active_loan(self):
        loan = self.approved()
        loan_services.create_loan_agreement(
            loan.pk, f"AG-TEST-{loan.pk}", timezone.localdate(),
            "Test agreement terms",
        )
        loan_services.accept_loan_agreement(loan.pk, self.client_a.user)
        return loan_services.disburse_loan(loan.pk, self.staff, self.bank.pk)

    def test_application_limits(self):
        for principal, months in [
            ("999", 12), ("50001", 12), ("5000", 2), ("5000", 25),
        ]:
            with self.subTest(principal=principal, months=months), self.assertRaises(BankError):
                self.apply(principal, months)
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        with self.assertRaises(BankError):
            self.apply()

    def test_only_deciders_can_approve(self):
        self.fund_savings()
        loan = self.apply()
        with self.assertRaises(BankError):
            loan_services.approve_loan(loan.pk, self.staff)
        loan_services.approve_loan(loan.pk, self.officer)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.APPROVED)
        self.assertEqual(loan.decided_by, self.officer)

    def test_cannot_approve_twice_or_own_loan(self):
        loan = self.approved()
        with self.assertRaises(BankError):
            loan_services.approve_loan(loan.pk, self.officer)
        own = Client.objects.create(
            user=self.officer,
            id_number_encrypted=b"x",
            id_number_hash="h-off",
        )
        own_loan = loan_services.apply_for_loan(
            own, self.product, "2000", 6, self.officer,
            purpose="Personal expenses",
        )
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
            loan_services.disburse_loan(loan.pk, self.staff, self.bank.pk)
        self.fund_savings()
        loan_services.approve_loan(loan.pk, self.officer)
        loan_services.create_loan_agreement(
            loan.pk, f"AG-TEST-{loan.pk}", timezone.localdate(),
            "Test agreement terms",
        )
        loan_services.accept_loan_agreement(loan.pk, self.client_a.user)
        other = make_bank_account(make_client("bob"), "OTHER")
        with self.assertRaises(BankError):
            loan_services.disburse_loan(loan.pk, self.staff, other.pk)
        self.assertFalse(LedgerEntry.objects.filter(
            loan=loan, entry_type=LedgerEntry.EntryType.LOAN_DISBURSEMENT,
        ).exists())

    def test_disburse_creates_schedule_and_credits_account(self):
        loan = self.active_loan()
        self.assertEqual(loan.status, Loan.Status.ACTIVE)
        self.assertEqual(self._fresh_bank_balance(), Decimal("15000.00"))
        items = list(loan.installments.all())
        self.assertEqual(len(items), 12)
        self.assertEqual(sum(i.principal_due for i in items), Decimal("12000.00"))
        self.assertTrue(LedgerEntry.objects.filter(
            loan=loan, entry_type=LedgerEntry.EntryType.LOAN_DISBURSEMENT,
        ).exists())

    def _fresh_bank_balance(self):
        self.bank.refresh_from_db()
        return self.bank.balance

    def test_payments_fill_installments_in_order_then_close_loan(self):
        loan = self.active_loan()
        first = loan.installments.get(number=1)
        half = (first.total_due / 2).quantize(Decimal("0.01"))
        loan_services.record_payment(loan.pk, half, self.staff)
        first.refresh_from_db()
        self.assertEqual(first.status, Installment.Status.DUE)
        loan_services.record_payment(loan.pk, first.total_due - half, self.staff)
        first.refresh_from_db()
        self.assertEqual(first.status, Installment.Status.PAID)
        self.assertEqual(loan.installments.get(number=2).amount_paid, Decimal("0"))
        remaining = sum(
            i.total_due - i.amount_paid
            for i in loan.installments.exclude(status="paid")
        )
        with self.assertRaises(BankError):
            loan_services.record_payment(loan.pk, remaining + Decimal("0.01"), self.staff)
        loan_services.record_payment(loan.pk, remaining, self.staff)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.PAID)
        with self.assertRaises(BankError):
            loan_services.record_payment(loan.pk, "1", self.staff)

    def test_only_staff_or_admin_record_payments(self):
        loan = self.active_loan()
        with self.assertRaises(BankError):
            loan_services.record_payment(loan.pk, "10", self.officer)
