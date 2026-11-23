from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render

from accounting.models import BankAccount, LedgerEntry
from accounts.decorators import role_required
from clients.models import Client
from loans.models import Loan
from savings.models import SavingsAccount


def mask_account_number(account_number):
    """Show only the last four digits of an account number."""
    if not account_number:
        return "Account number unavailable"

    return f"••••{account_number[-4:]}"


def get_activity_details(entry):
    """Identify the customer and account affected by a ledger entry."""
    bank_account = entry.bank_account
    savings_account = entry.savings_account
    loan = entry.loan

    client = None
    account_label = "Unlinked transaction"

    if bank_account:
        client = bank_account.client
        account_label = (
            f"Regular Account • "
            f"{mask_account_number(bank_account.account_number)}"
        )

    elif savings_account:
        client = savings_account.client
        account_label = (
            f"Savings Account • "
            f"{mask_account_number(savings_account.account_number)}"
        )

    elif loan:
        client = loan.client
        account_label = f"Loan #{loan.pk}"

    if client:
        customer_name = (
            client.user.get_full_name() or client.user.username
        )
    else:
        customer_name = "Customer not linked"

    if entry.created_by:
        processed_by = (
            entry.created_by.get_full_name()
            or entry.created_by.username
        )
    else:
        processed_by = "System"

    return {
        "created_at": entry.created_at,
        "customer": customer_name,
        "account": account_label,
        "activity": entry.get_entry_type_display(),
        "processed_by": processed_by,
        "amount": entry.amount,
    }


@role_required("staff")
def role_dashboard(request):
    role = request.user.role.name

    context = {
        "dashboard_role": role,
        "pending_count": Loan.objects.filter(
            status=Loan.Status.PENDING
        ).count(),
        "active_count": Loan.objects.filter(
            status=Loan.Status.ACTIVE
        ).count(),
    }

    if role == "admin":
        recent_entries = (
            LedgerEntry.objects
            .select_related(
                "created_by",
                "bank_account__client__user",
                "savings_account__client__user",
                "loan__client__user",
            )
            .order_by("-created_at", "-pk")[:8]
        )

        context.update({
            "total_clients": Client.objects.count(),
            "active_clients": Client.objects.filter(
                verification_status=Client.VerificationStatus.ACTIVE
            ).count(),
            "pending_clients": Client.objects.filter(
                verification_status=Client.VerificationStatus.PENDING
            ).count(),
            "total_regular_balance": (
                BankAccount.objects.filter(
                    status=BankAccount.Status.ACTIVE
                ).aggregate(total=Sum("balance"))["total"]
                or Decimal("0.00")
            ),
            "total_savings_balance": (
                SavingsAccount.objects.filter(
                    status=SavingsAccount.Status.ACTIVE
                ).aggregate(total=Sum("balance"))["total"]
                or Decimal("0.00")
            ),
            "outstanding_loan_principal": (
                Loan.objects.filter(
                    status=Loan.Status.ACTIVE
                ).aggregate(total=Sum("principal"))["total"]
                or Decimal("0.00")
            ),
            "recent_activity": [
                get_activity_details(entry)
                for entry in recent_entries
            ],
        })

    elif role == "loan_officer":
        context.update({
            "approved_count": Loan.objects.filter(
                status=Loan.Status.APPROVED
            ).count(),
            "paid_count": Loan.objects.filter(
                status=Loan.Status.PAID
            ).count(),
            "defaulted_count": Loan.objects.filter(
                status=Loan.Status.DEFAULTED
            ).count(),
            "review_queue": (
                Loan.objects.filter(
                    status=Loan.Status.PENDING
                )
                .select_related("client__user", "product")
                .order_by("applied_at", "pk")[:10]
            ),
            "recent_loans": (
                Loan.objects.select_related(
                    "client__user", "product"
                )
                .order_by("-applied_at", "-pk")[:6]
            ),
        })

    else:
        context.update({
            "pending_clients": Client.objects.filter(
                verification_status=Client.VerificationStatus.PENDING
            ).count(),
            "approved_for_release": Loan.objects.filter(
                status=Loan.Status.APPROVED
            ).count(),
            "savings_count": SavingsAccount.objects.filter(
                status=SavingsAccount.Status.ACTIVE
            ).count(),
            "pending_verifications": (
                Client.objects.filter(
                    verification_status=Client.VerificationStatus.PENDING
                )
                .select_related("user")
                .order_by("created_at", "pk")[:8]
            ),
            "release_queue": (
                Loan.objects.filter(
                    status=Loan.Status.APPROVED
                )
                .select_related("client__user", "product")
                .order_by("applied_at", "pk")[:8]
            ),
        })

    return render(request, "staff/home.html", context)