
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render

from accounting.models import BankAccount, LedgerEntry
from accounts.decorators import role_required
from clients.models import Client
from loans.models import Loan
from savings.models import SavingsAccount


@role_required("admin", "loan_officer", "staff")
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
            "recent_activity": (
                LedgerEntry.objects
                .select_related("created_by")
                .order_by("-created_at", "-pk")[:8]
            ),
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
