
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounting.money import BankError
from accounts.decorators import client_required, role_required
from savings.models import SavingsAccount

from . import services
from .agreement_pdf import generate_agreement_pdf
from .models import Loan, LoanAgreement, LoanProduct


STAFF = ("admin", "staff", "loan_officer")
DECIDERS = ("admin", "loan_officer")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise Http404


def _run(request, ok, func, *args):
    """Call a service and display its result."""
    try:
        func(*args)
        messages.success(request, ok)
    except (BankError, PermissionDenied) as e:
        messages.error(request, str(e) or "Not allowed.")


# ==========================================
# CLIENT PORTAL
# ==========================================

@client_required
def portal_loans(request):
    loans = (
        request.client.loans
        .select_related("product")
        .order_by("-applied_at")
    )

    return render(
        request,
        "portal/loans.html",
        {
            "loans": loans,
            "products": LoanProduct.objects.filter(
                is_active=True
            ),
        },
    )


@client_required
@require_POST
def portal_apply(request):
    product = get_object_or_404(
        LoanProduct,
        pk=_int(request.POST.get("product")),
        is_active=True,
    )

    try:
        term = int(request.POST.get("term_months", ""))
    except (TypeError, ValueError):
        messages.error(
            request,
            "Enter the term in whole months.",
        )
        return redirect("portal_loans")

    _run(
        request,
        "Application submitted.",
        services.apply_for_loan,
        request.client,
        product,
        request.POST.get("principal"),
        term,
        request.user,
    )

    return redirect("portal_loans")


# ==========================================
# CLIENT: VIEW LOAN AGREEMENT
# ==========================================

@client_required
def portal_loan_agreement(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related(
            "product",
            "client__user",
        ),
        pk=loan_id,
        client=request.client,
    )

    agreement = get_object_or_404(
        LoanAgreement,
        loan=loan,
    )

    return render(
        request,
        "portal/loan_agreement.html",
        {
            "loan": loan,
            "agreement": agreement,
        },
    )


# ==========================================
# CLIENT: ACCEPT AGREEMENT
# ==========================================

@client_required
@require_POST
def portal_accept_agreement(request, loan_id):
    loan = get_object_or_404(
        Loan,
        pk=loan_id,
        client=request.client,
    )

    if request.POST.get("accept") != "yes":
        messages.error(
            request,
            "Please confirm that you accept the agreement.",
        )
        return redirect(
            "portal_loan_agreement",
            loan_id=loan.pk,
        )

    _run(
        request,
        "Loan agreement accepted successfully.",
        services.accept_loan_agreement,
        loan.pk,
        request.user,
    )

    return redirect(
        "portal_loan_agreement",
        loan_id=loan.pk,
    )


# ==========================================
# STAFF: LOAN LIST
# ==========================================

@role_required(*STAFF)
def staff_loans(request):
    loans = (
        Loan.objects
        .select_related("client__user", "product")
        .order_by("-applied_at")[:100]
    )

    return render(
        request,
        "staff/loans.html",
        {"loans": loans},
    )


# ==========================================
# STAFF: LOAN DETAILS
# ==========================================

@role_required(*STAFF)
def staff_loan(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related(
            "client__user",
            "product",
        ),
        pk=loan_id,
    )

    agreement = LoanAgreement.objects.filter(
        loan=loan
    ).first()

    return render(
        request,
        "staff/loan_detail.html",
        {
            "loan": loan,
            "installments": loan.installments.order_by(
                "number"
            ),
            "accounts": loan.client.savings_accounts.all(),
            "agreement": agreement,
        },
    )


# ==========================================
# STAFF: APPROVE LOAN
# ==========================================

@role_required(*STAFF)
@require_POST
def staff_loan_approve(request, loan_id):
    _run(
        request,
        "Loan approved.",
        services.approve_loan,
        loan_id,
        request.user,
    )

    return redirect(
        "staff_loan",
        loan_id=loan_id,
    )


# ==========================================
# STAFF: REJECT LOAN
# ==========================================

@role_required(*STAFF)
@require_POST
def staff_loan_reject(request, loan_id):
    _run(
        request,
        "Loan rejected.",
        services.reject_loan,
        loan_id,
        request.user,
        request.POST.get("reason", "").strip(),
    )

    return redirect(
        "staff_loan",
        loan_id=loan_id,
    )


# ==========================================
# STAFF: CREATE LOAN AGREEMENT
# ==========================================

@role_required(*DECIDERS)
@require_POST
def staff_create_agreement(request, loan_id):
    loan = get_object_or_404(
        Loan,
        pk=loan_id,
    )

    agreement_number = f"AGR-{loan.pk:06d}"

    _run(
        request,
        "Loan agreement created.",
        services.create_loan_agreement,
        loan.pk,
        agreement_number,
        timezone.localdate(),
        (
            "The borrower agrees to repay the loan "
            "according to the agreed installment schedule. "
            "Late payments may result in penalties. "
            "The loan will only be disbursed after "
            "the borrower accepts this agreement."
        ),
    )

    return redirect(
        "staff_loan",
        loan_id=loan.pk,
    )


# ==========================================
# STAFF: DISBURSE LOAN
# ==========================================

@role_required(*STAFF)
@require_POST
def staff_loan_disburse(request, loan_id):
    loan = get_object_or_404(
        Loan,
        pk=loan_id,
    )

    account = get_object_or_404(
        SavingsAccount,
        pk=_int(request.POST.get("account")),
        client=loan.client,
    )

    _run(
        request,
        "Loan disbursed.",
        services.disburse_loan,
        loan.pk,
        request.user,
        account.pk,
    )

    return redirect(
        "staff_loan",
        loan_id=loan.pk,
    )


# ==========================================
# STAFF: RECORD PAYMENT
# ==========================================

@role_required(*STAFF)
@require_POST
def staff_loan_pay(request, loan_id):
    _run(request, "Payment recorded.", services.record_payment,
         loan_id, request.POST.get("amount"), request.user)
    return redirect("staff_loan", loan_id=loan_id)
