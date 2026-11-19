from datetime import date
from loans.models import LoanProduct
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounting.money import BankError
from accounts.decorators import client_required, role_required
from clients.models import Client
from savings.models import SavingsAccount

from . import services
from .models import Installment, Loan, LoanProduct

STAFF = ("admin", "staff", "loan_officer")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise Http404


def _run(request, ok, func, *args):
    """Call a service; show its error message instead of crashing."""
    try:
        func(*args)
        messages.success(request, ok)
    except (BankError, PermissionDenied) as e:
        messages.error(request, str(e) or "Not allowed.")


# ---------- client portal ----------

@client_required
def portal_loans(request):
    return render(request, "portal/loans.html", {
        "loans": request.client.loans.select_related("product").order_by("-applied_at"),
        "products": LoanProduct.objects.filter(is_active=True),
    })


@client_required
@require_POST
def portal_apply(request):
    if request.client.verification_status != Client.VerificationStatus.ACTIVE:
        messages.error(
            request,
            "Your account must be verified (Active) before you can apply for a loan.",
        )
        return redirect("portal_loans")

    if Installment.objects.filter(
        loan__client=request.client, status=Installment.Status.OVERDUE
    ).exists():
        messages.error(
            request,
            "You have an overdue loan. Please settle it before applying again.",
        )
        return redirect("portal_loans")

    product = get_object_or_404(
        LoanProduct, pk=_int(request.POST.get("product")), is_active=True
    )
    try:
        term = int(request.POST.get("term_months", ""))
    except ValueError:
        messages.error(request, "Enter the term in whole months.")
        return redirect("portal_loans")

    _run(request, "Application submitted.", services.apply_for_loan,
         request.client, product, request.POST.get("principal"), term, request.user)
    return redirect("portal_loans")


# ---------- staff ----------

@role_required(*STAFF)
def staff_loans(request):
    loans = Loan.objects.select_related("client__user", "product").order_by("-applied_at")[:100]
    return render(request, "staff/loans.html", {"loans": loans})


@role_required(*STAFF)
def staff_loan(request, loan_id):
    loan = get_object_or_404(Loan.objects.select_related("client__user", "product"), pk=loan_id)
    return render(request, "staff/loan_detail.html", {
        "loan": loan,
        "installments": loan.installments.order_by("number"),
        "accounts": loan.client.savings_accounts.all(),
        "eligibility": loan.eligibility_checks.order_by("-checked_at").first(),
    })


@role_required(*STAFF)
@require_POST
def staff_loan_approve(request, loan_id):
    _run(request, "Loan approved.", services.approve_loan, loan_id, request.user)
    return redirect("staff_loan", loan_id=loan_id)


@role_required(*STAFF)
@require_POST
def staff_loan_reject(request, loan_id):
    _run(request, "Loan rejected.", services.reject_loan,
         loan_id, request.user, request.POST.get("reason", "").strip())
    return redirect("staff_loan", loan_id=loan_id)


@role_required(*STAFF)
@require_POST
def staff_loan_disburse(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)
    # The account must belong to this loan's client.
    account = get_object_or_404(
        SavingsAccount, pk=_int(request.POST.get("account")), client=loan.client
    )
    _run(request, "Loan disbursed.", services.disburse_loan, loan.pk, request.user, account.pk)
    return redirect("staff_loan", loan_id=loan.pk)


@role_required(*STAFF)
@require_POST
def staff_loan_pay(request, loan_id):
    _run(request, "Payment recorded.", services.record_payment,
         loan_id, request.POST.get("amount"), request.user)
    return redirect("staff_loan", loan_id=loan_id)


# ---------- calendar ----------

@login_required
def calendar_page(request):
    if request.user.role.name not in STAFF + ("client",):
        raise PermissionDenied
    return render(request, "loans/calendar.html")


@login_required
def calendar_events(request):
    role = request.user.role.name
    qs = Installment.objects.select_related("loan__client__user", "loan__product")
    if role == "client":
        try:
            qs = qs.filter(loan__client=request.user.client_profile)
        except ObjectDoesNotExist:
            raise PermissionDenied
    elif role not in STAFF:
        raise PermissionDenied

    start = parse_date((request.GET.get("start") or "")[:10])
    end = parse_date((request.GET.get("end") or "")[:10])
    if start and end:
        qs = qs.filter(due_date__gte=start, due_date__lt=end)

    today = date.today()
    events = []
    for i in qs[:1000]:
        amount = i.principal_due + i.interest_due
        if i.status == "paid":
            color = "#198754"
        elif i.status == "overdue" or i.due_date < today:
            color = "#dc3545"
        else:
            color = "#0d6efd"
        title = f"₱ {amount:,.2f}"
        if role != "client":
            title = f"{i.loan.client} · {title}"
        event = {
            "title": title,
            "start": i.due_date.isoformat(),
            "color": color,
            "allDay": True,
        }
        if role != "client":
            event["url"] = f"/staff/loans/{i.loan_id}/"
        events.append(event)
    return JsonResponse(events, safe=False)