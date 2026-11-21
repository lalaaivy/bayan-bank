
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from .calculations import build_schedule, monthly_installment


class LoanCalculationTests(SimpleTestCase):

    def test_monthly_installment_with_zero_interest(self):
        result = monthly_installment(
            Decimal("12000.00"),
            Decimal("0.00"),
            12,
        )

        self.assertEqual(result, Decimal("1000.00"))

    def test_monthly_installment_with_interest(self):
        result = monthly_installment(
            Decimal("12000.00"),
            Decimal("12.00"),
            12,
        )

        self.assertGreater(result, Decimal("1000.00"))

    def test_schedule_has_correct_number_of_installments(self):
        schedule = build_schedule(
            Decimal("12000.00"),
            Decimal("12.00"),
            12,
            date(2026, 1, 1),
        )

        self.assertEqual(len(schedule), 12)

    def test_schedule_final_balance_is_zero(self):
        schedule = build_schedule(
            Decimal("12000.00"),
            Decimal("12.00"),
            12,
            date(2026, 1, 1),
        )

        self.assertEqual(
            schedule[-1]["balance"],
            Decimal("0.00"),
        )

    def test_schedule_principal_totals_original_loan(self):
        principal = Decimal("12000.00")

        schedule = build_schedule(
            principal,
            Decimal("12.00"),
            12,
            date(2026, 1, 1),
        )

        total_principal = sum(
            (row["principal_due"] for row in schedule),
            Decimal("0.00"),
        )

        self.assertEqual(total_principal, principal)

    def test_schedule_due_dates_are_monthly(self):
        schedule = build_schedule(
            Decimal("12000.00"),
            Decimal("12.00"),
            3,
            date(2026, 1, 15),
        )

        self.assertEqual(
            schedule[0]["due_date"],
            date(2026, 2, 15),
        )
        self.assertEqual(
            schedule[1]["due_date"],
            date(2026, 3, 15),
        )
        self.assertEqual(
            schedule[2]["due_date"],
            date(2026, 4, 15),
        )

    def test_invalid_principal_is_rejected(self):
        with self.assertRaises(ValueError):
            monthly_installment(
                Decimal("0.00"),
                Decimal("12.00"),
                12,
            )

    def test_invalid_term_is_rejected(self):
        with self.assertRaises(ValueError):
            monthly_installment(
                Decimal("12000.00"),
                Decimal("12.00"),
                0,
            )

    def test_negative_interest_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            monthly_installment(
                Decimal("12000.00"),
                Decimal("-1.00"),
                12,
            )
