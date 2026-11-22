from decimal import Decimal

from django.core.management.base import BaseCommand

from loans.models import LoanProduct, LoanRule

PRODUCTS = [
    # name, yearly rate, min amount, max amount, min months, max months, min credit score
    ("Personal Loan", "18", "5000", "300000", 3, 24, 600),
    ("Business Loan", "16", "25000", "1000000", 3, 36, 600),
    ("Emergency Loan", "12", "2000", "50000", 3, 12, 600),
]


class Command(BaseCommand):
    help = "Create the demo loan products and their eligibility rules."

    def handle(self, *args, **options):
        for name, rate, low, high, min_m, max_m, score in PRODUCTS:
            product, created = LoanProduct.objects.get_or_create(
                name=name,
                defaults={
                    "annual_rate": Decimal(rate),
                    "min_amount": Decimal(low),
                    "max_amount": Decimal(high),
                    "min_months": min_m,
                    "max_months": max_m,
                    "is_active": True,
                },
            )
            LoanRule.objects.get_or_create(
                product=product, defaults={"minimum_credit_score": score}
            )
            self.stdout.write(f"{'Created' if created else 'Already exists'}: {name}")