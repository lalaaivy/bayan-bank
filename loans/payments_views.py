from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounting.money import BankError
from accounts.decorators import role_required

from .models import Loan, LoanPayment
from .services import record_payment


VIEWERS = ("admin", "staff")
CASHIERS = ("staff",)


@role_required(*VIEWERS)
def staff_payments(request):
    search = request.GET.get("q", "").strip()

    payments = (
        LoanPayment.objects
        .select_related(
            "loan",
            "loan__client__user",
            "recorded_by",
        )
        .order_by("-payment_date")
    )

    active_loans = (
        Loan.objects
        .filter(status=Loan.Status.ACTIVE)
        .select_related("client__user", "product")
        .order_by("-applied_at")
    )

    if search:
        payment_filters = (
            Q(loan__client__user__username__icontains=search)
            | Q(loan__client__user__first_name__icontains=search)
            | Q(loan__client__user__last_name__icontains=search)
        )

        loan_filters = (
            Q(client__user__username__icontains=search)
            | Q(client__user__first_name__icontains=search)
            | Q(client__user__last_name__icontains=search)
        )

        if search.isdigit():
            payment_filters |= Q(loan_id=int(search))
            loan_filters |= Q(pk=int(search))

        payments = payments.filter(payment_filters)
        active_loans = active_loans.filter(loan_filters)

    return render(
        request,
        "staff/payments.html",
        {
            "payments": payments[:100],
            "active_loans": active_loans[:100],
            "search": search,
            "can_record": request.user.role.name in CASHIERS,
        },
    )


@role_required(*CASHIERS)
@require_POST
def staff_record_payment(request):
    loan_id = request.POST.get("loan_id")
    amount = request.POST.get("amount")

    loan = get_object_or_404(
        Loan,
        pk=loan_id,
    )

    try:
        record_payment(
            loan.pk,
            amount,
            request.user,
        )
        messages.success(
            request,
            f"Payment recorded successfully for Loan #{loan.pk}.",
        )

    except BankError as error:
        messages.error(request, str(error))

    return redirect("staff_payments")