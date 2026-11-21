
import os
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from accounting.money import BankError
from accounts.decorators import client_required, role_required
from clients.models import Client
from savings.models import SavingsAccount

from . import services
from .agreement_pdf import generate_agreement_pdf
from .models import (
    Installment,
    Loan,
    LoanAgreement,
    LoanDocument,
    LoanProduct,
)

STAFF = ("admin", "staff", "loan_officer")
DECIDERS = ("admin", "loan_officer")

MAX_DOCUMENT_SIZE = 5 * 1024 * 1024
MAX_DOCUMENTS = 5
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}


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


def _validate_loan_documents(files):
    """Validate uploaded loan supporting documents."""
    if len(files) > MAX_DOCUMENTS:
        raise BankError(
            f"You can upload a maximum of {MAX_DOCUMENTS} supporting documents."
        )

    for uploaded_file in files:
        extension = os.path.splitext(uploaded_file.name)[1].lower()

        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise BankError(
                f"{uploaded_file.name}: Only PDF, JPG, JPEG, and PNG files are allowed."
            )

        if uploaded_file.size > MAX_DOCUMENT_SIZE:
            raise BankError(
                f"{uploaded_file.name}: File size must not exceed 5 MB."
            )

        if uploaded_file.size == 0:
            raise BankError(f"{uploaded_file.name}: Empty files are not allowed.")

        if uploaded_file.content_type not in ALLOWED_DOCUMENT_TYPES:
            raise BankError(
                f"{uploaded_file.name}: Unsupported file type."
            )


# ==========================================
# CLIENT PORTAL
# ==========================================

@client_required
def portal_loans(request):
    loans = (
        request.client.loans
        .select_related("product")
        .prefetch_related("documents")
        .order_by("-applied_at")
    )

    return render(request, "portal/loans.html", {
        "loans": loans,
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

    product = get_object_or_404(
        LoanProduct,
        pk=_int(request.POST.get("product")),
        is_active=True,
    )

    try:
        term = int(request.POST.get("term_months", ""))
    except (TypeError, ValueError):
        messages.error(request, "Enter the term in whole months.")
        return redirect("portal_loans")

    purpose = (request.POST.get("purpose") or "").strip()
    documents = request.FILES.getlist("documents")
    document_type = request.POST.get("document_type", LoanDocument.DocumentType.OTHER)

    if document_type not in LoanDocument.DocumentType.values:
        messages.error(request, "Select a valid supporting document type.")
        return redirect("portal_loans")

    try:
        if not purpose:
            raise BankError("Please provide the purpose of your loan application.")

        if len(purpose) > 1000:
            raise BankError("Loan purpose cannot exceed 1,000 characters.")

        _validate_loan_documents(documents)

        loan = services.apply_for_loan(
            request.client,
            product,
            request.POST.get("principal"),
            term,
            request.user,
            purpose,
        )

        for uploaded_file in documents:
            LoanDocument.objects.create(
                loan=loan,
                document_type=document_type,
                file=uploaded_file,
                uploaded_by=request.user,
            )

        messages.success(request, "Loan application submitted successfully.")

    except BankError as e:
        messages.error(request, str(e) or "Unable to submit loan application.")

    return redirect("portal_loans")


# ==========================================
# LOAN DOCUMENT DOWNLOAD
# ==========================================

@login_required
def loan_document_download(request, document_id):
    document = get_object_or_404(
        LoanDocument.objects.select_related("loan__client__user"),
        pk=document_id,
    )

    role = request.user.role.name

    if role == "client":
        if document.loan.client.user_id != request.user.pk:
            raise PermissionDenied
    elif role not in STAFF:
        raise PermissionDenied

    try:
        file_handle = document.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("The requested document could not be found.")

    filename = os.path.basename(document.file.name)

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
    )


# ==========================================
# LOAN AGREEMENT
# ==========================================

@client_required
def portal_loan_agreement(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related("product", "client__user"),
        pk=loan_id,
        client=request.client,
    )

    agreement = get_object_or_404(LoanAgreement, loan=loan)

    return render(request, "portal/loan_agreement.html", {
        "loan": loan,
        "agreement": agreement,
    })


@client_required
@require_POST
def portal_accept_agreement(request, loan_id):
    loan = get_object_or_404(
        Loan,
        pk=loan_id,
        client=request.client,
    )

    if request.POST.get("accept") != "yes":
        messages.error(request, "Please confirm that you accept the agreement.")
        return redirect("portal_loan_agreement", loan_id=loan.pk)

    _run(
        request,
        "Loan agreement accepted successfully.",
        services.accept_loan_agreement,
        loan.pk,
        request.user,
    )

    return redirect("portal_loan_agreement", loan_id=loan.pk)


@login_required
def loan_agreement_pdf(request, loan_id):
    """Download the agreement as a PDF (the borrower or loan staff only)."""
    loan = get_object_or_404(
        Loan.objects.select_related("product", "client__user"),
        pk=loan_id,
    )

    role = request.user.role.name

    if role == "client":
        if loan.client.user_id != request.user.pk:
            raise PermissionDenied
    elif role not in STAFF:
        raise PermissionDenied

    agreement = get_object_or_404(LoanAgreement, loan=loan)

    try:
        pdf = generate_agreement_pdf(loan, agreement)
    except TypeError:
        pdf = generate_agreement_pdf(agreement)

    if hasattr(pdf, "getvalue"):
        pdf = pdf.getvalue()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{agreement.agreement_number}.pdf"'
    )

    return response


# ==========================================
# STAFF
# ==========================================

@role_required(*STAFF)
def staff_loans(request):
    loans = (
        Loan.objects.select_related("client__user", "product")
        .order_by("-applied_at")[:100]
    )

    return render(request, "staff/loans.html", {"loans": loans})


@role_required(*STAFF)
def staff_loan(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related("client__user", "product"),
        pk=loan_id,
    )

    agreement = LoanAgreement.objects.filter(loan=loan).first()

    return render(request, "staff/loan_detail.html", {
        "loan": loan,
        "installments": loan.installments.order_by("number"),
        "accounts": loan.client.savings_accounts.all(),
        "agreement": agreement,
        "eligibility": loan.eligibility_checks.order_by("-checked_at").first(),
        "documents": loan.documents.order_by("-uploaded_at"),
    })


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

    return redirect("staff_loan", loan_id=loan_id)


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

    return redirect("staff_loan", loan_id=loan_id)


@role_required(*DECIDERS)
@require_POST
def staff_create_agreement(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)

    _run(
        request,
        "Loan agreement created.",
        services.create_loan_agreement,
        loan.pk,
        f"AGR-{loan.pk:06d}",
        timezone.localdate(),
        (
            "The borrower agrees to repay the loan "
            "according to the agreed installment schedule. "
            "Late payments may result in penalties. "
            "The loan will only be disbursed after "
            "the borrower accepts this agreement."
        ),
    )

    return redirect("staff_loan", loan_id=loan.pk)


@role_required(*STAFF)
@require_POST
def staff_loan_disburse(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)

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

    return redirect("staff_loan", loan_id=loan.pk)


@role_required(*STAFF)
@require_POST
def staff_loan_pay(request, loan_id):
    _run(
        request,
        "Payment recorded.",
        services.record_payment,
        loan_id,
        request.POST.get("amount"),
        request.user,
    )

    return redirect("staff_loan", loan_id=loan_id)


# ==========================================
# CALENDAR
# ==========================================

@login_required
def calendar_page(request):
    if request.user.role.name not in STAFF + ("client",):
        raise PermissionDenied

    return render(request, "loans/calendar.html")


@login_required
def calendar_events(request):
    role = request.user.role.name

    qs = Installment.objects.select_related(
        "loan__client__user",
        "loan__product",
    )

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

    for installment in qs[:1000]:
        amount = installment.principal_due + installment.interest_due

        if installment.status == "paid":
            color = "#198754"
        elif installment.status == "overdue" or installment.due_date < today:
            color = "#dc3545"
        else:
            color = "#0d6efd"

        title = f"₱ {amount:,.2f}"

        if role != "client":
            title = f"{installment.loan.client} · {title}"

        event = {
            "title": title,
            "start": installment.due_date.isoformat(),
            "color": color,
            "allDay": True,
        }

        if role != "client":
            event["url"] = f"/staff/loans/{installment.loan_id}/"

        events.append(event)

    return JsonResponse(events, safe=False)
