import csv
import secrets
import calendar
import json
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO

from django.db.models import Count
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounting.models import BankAccount, LedgerEntry
from accounting.money import BankError
from audit.models import AuditLog
from audit.services import log
from clients.models import Client, ClientDocument
from loans import services as loan_services
from loans.calculations import build_schedule
from loans.models import (
    Disbursement,
    EligibilityCheck,
    Installment,
    Loan,
    LoanAgreement,
    LoanPayment,
    LoanProduct,
    LoanRule,
)
from notifications.models import Notification
from savings.models import SavingsAccount, SavingsDeposit

from .decorators import client_required, role_required
from .forms import (
    ClientCreditScoreForm,
    ClientDocumentForm,
    ClientProfileForm,
    EmployeeUserCreateForm,
    EmployeeUserEditForm,
    RegisterForm,
)
from .models import Role, User


@login_required
def home(request):
    role = request.user.role.name

    destinations = {
        "client": "portal_home",
        "staff": "staff_home",
        "loan_officer": "officer_home",
        "admin": "admin_home",
    }

    return redirect(destinations.get(role, "login"))


@client_required
def portal_home(request):
    client = request.client

    bank_account = BankAccount.objects.filter(
        client=client
    ).first()

    bank_balance = (
        bank_account.balance
        if bank_account
        else Decimal("0.00")
    )

    savings_account = SavingsAccount.objects.filter(
        client=client
    ).first()

    accounts = SavingsAccount.objects.filter(
        client=client
    )

    balance = (
        accounts.aggregate(total=Sum("balance"))["total"]
        or Decimal("0.00")
    )

    released_deposits = SavingsDeposit.objects.filter(
        savings_account__client=client,
        status=SavingsDeposit.Status.RELEASED,
    )

    interest_summary = released_deposits.aggregate(
        total=Sum("interest_amount")
    )

    total_interest = (
        interest_summary["total"]
        or Decimal("0.00")
    )

    latest_interest = (
        released_deposits
        .order_by("-released_at", "-id")
        .first()
    )

    if latest_interest:
        latest_interest.posted_at = latest_interest.released_at

    loans = (
        Loan.objects.filter(client=client)
        .select_related("product")
        .order_by("-applied_at")
    )

    bank_transactions = (
        LedgerEntry.objects.filter(
            Q(bank_account__client=client)
            | Q(savings_account__client=client)
            | Q(loan__client=client)
        )
        .select_related(
            "bank_account",
            "savings_account",
            "loan",
        )
        .order_by("-created_at", "-id")[:5]
    )

    latest_document = client.documents.order_by(
        "-uploaded_at"
    ).first()

    context = {
        "client": client,
        "bank_account": bank_account,
        "bank_balance": bank_balance,
        "savings_account": savings_account,
        "accounts": accounts,
        "balance": balance,
        "loans": loans,
        "recent_transactions": bank_transactions,
        "bank_transactions": bank_transactions,
        "latest_document": latest_document,
        "total_interest": total_interest,
        "latest_interest": latest_interest,
    }

    return render(
        request,
        "portal/home.html",
        context,
    )


@role_required("staff", "admin", "loan_officer")
def staff_home(request):
    context = {
        "pending_count": Loan.objects.filter(
            status=Loan.Status.PENDING
        ).count(),
        "active_count": Loan.objects.filter(
            status=Loan.Status.ACTIVE
        ).count(),
    }

    return render(request, "staff/home.html", context)


@role_required("loan_officer", "admin")
def officer_home(request):
    return render(request, "officer/home.html")


@role_required("admin")
def admin_home(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Actual client and loan statistics
    active_clients = Client.objects.filter(
        verification_status=Client.VerificationStatus.ACTIVE
    ).count()

    active_loans = Loan.objects.filter(
        status=Loan.Status.ACTIVE
    ).count()

    pending_applications = Loan.objects.filter(
        status=Loan.Status.PENDING
    ).count()

    # Total loan payments collected during the current month
    monthly_collections = (
        LedgerEntry.objects.filter(
            entry_type=LedgerEntry.EntryType.LOAN_PAYMENT,
            created_at__date__gte=month_start,
            created_at__date__lte=today,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    # Latest actual banking transactions
    recent_activity = list(
        LedgerEntry.objects.select_related(
            "bank_account__client__user",
            "savings_account__client__user",
            "loan__client__user",
            "created_by",
        ).order_by("-created_at", "-id")[:8]
    )

    for entry in recent_activity:
        # Identify the customer affected by the transaction.
        if entry.bank_account_id:
            customer = entry.bank_account.client
            account_number = entry.bank_account.account_number
            account_type = "Regular Account"

        elif entry.savings_account_id:
            customer = entry.savings_account.client
            account_number = entry.savings_account.account_number
            account_type = "Savings Account"

        elif entry.loan_id:
            customer = entry.loan.client
            account_number = None
            account_type = f"Loan #{entry.loan_id}"

        else:
            customer = None
            account_number = None
            account_type = "N/A"

        if customer:
            entry.customer_name = (
                customer.user.get_full_name()
                or customer.user.username
            )
        else:
            entry.customer_name = "Unknown"

        if account_number:
            entry.account_display = (
                f"{account_type} •••• {account_number[-4:]}"
            )
        else:
            entry.account_display = account_type

        entry.processor_name = (
            entry.created_by.get_full_name()
            or entry.created_by.username
            if entry.created_by
            else "System"
        )

        entry.activity_label = entry.get_entry_type_display()

    context = {
        "active_clients": active_clients,
        "active_loans": active_loans,
        "monthly_collections": monthly_collections,
        "pending_applications": pending_applications,
        "recent_activity": recent_activity,
        "dashboard_date": today,
    }

    return render(
        request,
        "adminpanel/home.html",
        context,
    )


def _demo_form(request, template, destination):
    if request.method == "POST":
        messages.success(request, "Saved (demo)")
        return redirect(destination)

    return render(request, template)


# ---------- client portal ----------

@role_required("client")
def loan_detail(request):
    return render(request, "portal/loan_detail.html")


@client_required
def upload_id(request):
    client = request.client

    allowed = (
        Client.VerificationStatus.PENDING,
        Client.VerificationStatus.REJECTED,
    )

    if client.verification_status not in allowed:
        messages.info(
            request,
            "ID upload is not needed for your account status.",
        )
        return redirect("portal_home")

    form = ClientDocumentForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.client = client
        document.save()

        client.verification_status = Client.VerificationStatus.PENDING
        client.save(update_fields=["verification_status"])

        log(request.user, "upload_id", document)

        messages.success(
            request,
            "ID uploaded. Staff will review it and update your status.",
        )

        return redirect("portal_home")

    return render(
        request,
        "portal/upload_id.html",
        {"form": form, "client": client},
    )


@role_required("client")
def accept_agreement(request):
    return _demo_form(
        request,
        "portal/accept_agreement.html",
        "loan_detail",
    )


@client_required
def notifications(request):
    if request.method == "POST":
        notification_id = request.POST.get("notification_id")

        notification = get_object_or_404(
            Notification,
            pk=notification_id,
            user=request.user,
        )

        notification.is_read = True
        notification.save(update_fields=["is_read"])

        messages.success(request, "Notification marked as read.")
        return redirect(request.path)

    notification_list = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at", "-id")

    unread_count = notification_list.filter(is_read=False).count()

    context = {
        "notifications": notification_list,
        "unread_count": unread_count,
    }

    return render(request, "portal/notifications.html", context)


@role_required("client")
def apply_loan(request):
    return _demo_form(
        request,
        "portal/apply_loan.html",
        "apply_loan",
    )


@client_required
def client_profile(request):
    client = request.client

    return render(
        request,
        "portal/profile.html",
        {"client": client},
    )


@client_required
def edit_client_profile(request):
    client = request.client

    form = ClientProfileForm(
        request.POST or None,
        user=request.user,
        client=client,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(
            request,
            "Your profile has been updated successfully.",
        )

        return redirect("client_profile")

    return render(
        request,
        "portal/profile_edit.html",
        {
            "form": form,
            "client": client,
        },
    )


@role_required("client")
def change_password(request):
    return _demo_form(
        request,
        "portal/change_password.html",
        "client_profile",
    )


# ---------- registration ----------

def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        client = form.save()

        login(
            request,
            client.user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        messages.success(
            request,
            f"Registered! Your Client ID is {client.client_code}. "
            "Upload your ID so staff can verify your account.",
        )

        return redirect("upload_id")

    return render(
        request,
        "registration/register.html",
        {"form": form},
    )


def complete_profile(request):
    return _demo_form(
        request,
        "registration/complete_profile.html",
        "complete_profile",
    )


# ---------- staff ----------

@role_required("staff", "admin")
def staff_clients(request):
    clients = (
        Client.objects.select_related("user")
        .order_by("-created_at")
    )

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if q:
        clients = clients.filter(
            Q(user__username__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(user__email__icontains=q)
            | Q(phone__icontains=q)
        )

    if status_filter in Client.VerificationStatus.values:
        clients = clients.filter(
            verification_status=status_filter
        )

    client_list = list(clients[:200])

    for client in client_list:
        client.loans_count = Loan.objects.filter(
            client=client
        ).count()

        client.savings_balance = (
            SavingsAccount.objects.filter(client=client)
            .aggregate(total=Sum("balance"))["total"]
            or Decimal("0.00")
        )

    context = {
        "clients": client_list,
        "q": q,
        "status": status_filter,
        "statuses": Client.VerificationStatus.choices,
    }

    return render(request, "staff/clients.html", context)


@role_required("staff", "admin")
def staff_add_client(request):
    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        client = form.save()

        log(
            request.user,
            "create_client",
            client,
            ip=request.META.get("REMOTE_ADDR"),
        )

        messages.success(
            request,
            f"Client {client.client_code} created successfully.",
        )

        return redirect("staff_client_detail", client_id=client.pk)

    return render(
        request,
        "staff/add_client.html",
        {"form": form},
    )


@role_required("staff", "admin")
def staff_client_detail(request, client_id):
    client = get_object_or_404(
        Client.objects.select_related("user"),
        pk=client_id,
    )

    credit_score_form = ClientCreditScoreForm(
        request.POST or None,
        initial={"credit_score": client.credit_score},
    )

    if request.method == "POST":
        if credit_score_form.is_valid():
            new_score = credit_score_form.cleaned_data["credit_score"]
            reason = credit_score_form.cleaned_data["reason"]

            with transaction.atomic():
                locked_client = get_object_or_404(
                    Client.objects.select_for_update(),
                    pk=client_id,
                )

                previous_score = locked_client.credit_score

                locked_client.credit_score = new_score
                locked_client.save(update_fields=["credit_score"])

                log(
                    request.user,
                    "update_client_credit_score",
                    locked_client,
                    ip=request.META.get("REMOTE_ADDR"),
                    previous_score=previous_score,
                    new_score=new_score,
                    reason=reason,
                )

            messages.success(
                request,
                f"Credit score updated successfully from "
                f"{previous_score} to {new_score}.",
            )

            return redirect(
                "staff_client_detail",
                client_id=client_id,
            )

        messages.error(
            request,
            "Please correct the errors in the credit score form.",
        )

    client.refresh_from_db()

    loans = (
        Loan.objects.filter(client=client)
        .select_related("product", "decided_by")
        .order_by("-applied_at")
    )

    bank_account = BankAccount.objects.filter(
        client=client
    ).first()

    savings_accounts = (
        SavingsAccount.objects.filter(client=client)
        .order_by("-opened_at")
    )

    total_savings = (
        savings_accounts.aggregate(total=Sum("balance"))["total"]
        or Decimal("0.00")
    )

    transactions = (
        LedgerEntry.objects.filter(
            Q(bank_account__client=client)
            | Q(savings_account__client=client)
            | Q(loan__client=client)
        )
        .select_related(
            "bank_account",
            "savings_account",
            "loan",
            "created_by",
        )
        .order_by("-created_at", "-id")[:100]
    )

    context = {
        "client": client,
        "bank_account": bank_account,
        "loans": loans,
        "savings_accounts": savings_accounts,
        "total_savings": total_savings,
        "transactions": transactions,
        "credit_score_form": credit_score_form,
    }

    return render(
        request,
        "staff/client_detail.html",
        context,
    )


@role_required("staff", "admin")
def staff_payments(request):
    return _demo_form(
        request,
        "staff/payments.html",
        "staff_receipt",
    )


@role_required("staff", "admin")
def staff_payment_history(request):
    return render(request, "staff/payment_history.html")


@role_required("staff", "admin")
def staff_savings(request):
    return _demo_form(
        request,
        "staff/savings.html",
        "staff_savings",
    )


@role_required("staff", "admin")
def verify_clients(request):
    pending = (
        Client.objects.select_related("user")
        .filter(
            verification_status=Client.VerificationStatus.PENDING
        )
        .order_by("created_at")
    )

    return render(
        request,
        "staff/verify_clients.html",
        {"clients": pending},
    )


@role_required("staff", "admin")
def verify_client_detail(request, client_id):
    client = get_object_or_404(
        Client.objects.select_related("user"),
        pk=client_id,
    )

    document = client.documents.order_by("-uploaded_at").first()

    if request.method == "POST":
        decision = request.POST.get("decision")

        if decision not in ("approve", "reject"):
            messages.error(request, "Please choose Approve or Reject.")

        else:
            with transaction.atomic():
                locked_client = get_object_or_404(
                    Client.objects.select_for_update(),
                    pk=client_id,
                )

                is_pending = (
                    locked_client.verification_status
                    == Client.VerificationStatus.PENDING
                )

                if not is_pending:
                    messages.error(
                        request,
                        "This client is no longer pending verification.",
                    )

                elif (
                    decision == "approve"
                    and not locked_client.documents.exists()
                ):
                    messages.error(
                        request,
                        "Cannot approve: this client has not uploaded an ID yet.",
                    )

                else:
                    approved = decision == "approve"

                    locked_client.verification_status = (
                        Client.VerificationStatus.ACTIVE
                        if approved
                        else Client.VerificationStatus.REJECTED
                    )

                    locked_client.verified_by = request.user
                    locked_client.verified_at = timezone.now()

                    locked_client.save(
                        update_fields=[
                            "verification_status",
                            "verified_by",
                            "verified_at",
                        ]
                    )

                    latest_document = (
                        locked_client.documents
                        .order_by("-uploaded_at")
                        .first()
                    )

                    if latest_document is not None:
                        latest_document.status = (
                            ClientDocument.Status.VERIFIED
                            if approved
                            else ClientDocument.Status.REJECTED
                        )

                        latest_document.reviewed_by = request.user
                        latest_document.reviewed_at = timezone.now()
                        latest_document.remark = request.POST.get(
                            "remark",
                            "",
                        ).strip()[:255]

                        latest_document.save(
                            update_fields=[
                                "status",
                                "reviewed_by",
                                "reviewed_at",
                                "remark",
                            ]
                        )

                    if approved:
                        bank_account = BankAccount.objects.filter(
                            client=locked_client
                        ).first()

                        if bank_account is None:
                            while True:
                                account_number = str(
                                    secrets.randbelow(9_000_000_000)
                                    + 1_000_000_000
                                )

                                if not BankAccount.objects.filter(
                                    account_number=account_number
                                ).exists():
                                    break

                            bank_account = BankAccount.objects.create(
                                client=locked_client,
                                account_number=account_number,
                            )

                    log(
                        request.user,
                        f"{decision}_client",
                        locked_client,
                    )

                    result = "approved" if approved else "rejected"

                    messages.success(
                        request,
                        f"{locked_client.client_code} {result}."
                        + (
                            f" Regular bank account created: "
                            f"{bank_account.account_number}."
                            if approved
                            else ""
                        ),
                    )

                    return redirect("verify_clients")

    id_number = str(client.get_id_number())
    masked_id = "****" + id_number[-4:]

    context = {
        "client": client,
        "document": document,
        "masked_id": masked_id,
    }

    return render(
        request,
        "staff/verify_client_detail.html",
        context,
    )


@role_required("staff", "admin")
def client_document_file(request, doc_id, side):
    """Sends a private ID image to staff. Images are not in a public folder."""

    document = get_object_or_404(ClientDocument, pk=doc_id)

    if side == "front":
        image = document.front_image
    elif side == "back":
        image = document.back_image
    else:
        raise Http404

    if not image:
        raise Http404

    return FileResponse(image.open("rb"))


# ---------- staff loan release ----------

@role_required("staff", "admin")
def release_loans(request):
    """
    Show real approved loans that have signed agreements,
    have not been disbursed, and have an active regular bank account.
    """

    signed_agreements = LoanAgreement.objects.filter(
        signed_at__isnull=False,
    ).order_by("-signed_at", "-id")

    disbursed_loan_ids = Disbursement.objects.values_list(
        "loan_id",
        flat=True,
    )

    loans = (
        Loan.objects.filter(
            pk__in=signed_agreements.values("loan_id"),
            status=Loan.Status.APPROVED,
        )
        .exclude(pk__in=disbursed_loan_ids)
        .select_related("client__user", "product")
        .order_by("-applied_at", "-id")
    )

    loan_list = list(loans)

    loan_ids = [loan.pk for loan in loan_list]
    client_ids = [loan.client_id for loan in loan_list]

    agreements_by_loan = {
        agreement.loan_id: agreement
        for agreement in signed_agreements.filter(
            loan_id__in=loan_ids
        )
    }

    accounts = (
        BankAccount.objects.filter(
            client_id__in=client_ids,
            status=BankAccount.Status.ACTIVE,
        )
        .order_by("id")
    )

    accounts_by_client = {}

    for account in accounts:
        accounts_by_client.setdefault(account.client_id, account)

    for loan in loan_list:
        loan.release_agreement = agreements_by_loan.get(loan.pk)
        loan.release_bank_account = accounts_by_client.get(
            loan.client_id
        )

    context = {
        "loans": loan_list,
    }

    return render(
        request,
        "staff/release_loan.html",
        context,
    )


@role_required("staff", "admin")
def confirm_loan_release(request):
    """
    Process an actual loan disbursement.

    This view delegates all financial operations and validation
    to the existing loans.services.disburse_loan() function.
    """

    if request.method != "POST":
        return redirect("release_loans")

    loan_id = request.POST.get("loan_id")
    bank_account_id = request.POST.get("bank_account_id")

    if not loan_id or not bank_account_id:
        messages.error(
            request,
            "Missing loan or bank account information. "
            "Please try again.",
        )
        return redirect("release_loans")

    try:
        loan_id = int(loan_id)
        bank_account_id = int(bank_account_id)

        loan = loan_services.disburse_loan(
            loan_id,
            request.user,
            bank_account_id,
        )

    except (TypeError, ValueError):
        messages.error(
            request,
            "Invalid loan or bank account selection.",
        )
        return redirect("release_loans")

    except BankError as error:
        messages.error(request, str(error))
        return redirect("release_loans")

    messages.success(
        request,
        f"Loan #{loan.pk} was successfully released. "
        f"₱{loan.principal:,.2f} was credited to the client's "
        "regular bank account.",
    )

    return redirect("release_loans")


@role_required("staff", "admin")
def staff_receipt(request):
    return render(request, "staff/receipt.html")


# ---------- loan officer ----------

@role_required("loan_officer", "admin")
def loan_applications(request):
    loans = (
        Loan.objects.select_related("client__user", "product")
        .order_by("-applied_at")
    )

    status_filter = request.GET.get("status", "").title()

    if status_filter in {"Pending", "Approved", "Rejected"}:
        loans = loans.filter(status=status_filter.lower())

    applications = [
        {
            "pk": loan.pk,
            "reference": (
                f"APP-{loan.applied_at.year}-{loan.pk:04d}"
            ),
            "name": (
                loan.client.user.get_full_name()
                or loan.client.user.username
            ),
            "product": loan.product.name,
            "amount": f"{loan.principal:,.2f}",
            "date": loan.applied_at.strftime("%b %d, %Y"),
            "status": loan.get_status_display(),
        }
        for loan in loans[:200]
    ]

    return render(
        request,
        "officer/applications.html",
        {
            "applications": applications,
            "status_filter": status_filter,
        },
    )


@role_required("loan_officer", "admin")
def officer_loans(request):
    loans = (
        Loan.objects.select_related(
            "client__user",
            "product",
        )
        .order_by("-applied_at", "-id")
    )

    status_filter = request.GET.get("status", "").strip().lower()

    valid_statuses = {
        Loan.Status.PENDING,
        Loan.Status.APPROVED,
        Loan.Status.REJECTED,
        Loan.Status.ACTIVE,
    }

    if status_filter in valid_statuses:
        loans = loans.filter(status=status_filter)

    context = {
        "loans": loans,
        "status_filter": status_filter,
    }

    return render(
        request,
        "officer/loans.html",
        context,
    )


@role_required("loan_officer", "admin")
def loan_application_detail(request, loan_id):
    loan = get_object_or_404(
        Loan.objects.select_related(
            "client__user",
            "product",
        ),
        pk=loan_id,
    )

    if request.method == "POST":
        decision = request.POST.get("decision", "").strip()
        remarks = request.POST.get("remarks", "").strip()

        if loan.status != Loan.Status.PENDING:
            messages.error(
                request,
                "This application is no longer pending review.",
            )
            return redirect(
                "loan_application_detail",
                loan_id=loan.pk,
            )

        try:
            if decision == "approved":
                loan_services.approve_loan(
                    loan.pk,
                    request.user,
                )

                messages.success(
                    request,
                    "Loan application approved successfully.",
                )

            elif decision == "rejected":
                if not remarks:
                    messages.error(
                        request,
                        "Please provide a reason for rejecting this application.",
                    )
                    return redirect(
                        "loan_application_detail",
                        loan_id=loan.pk,
                    )

                loan_services.reject_loan(
                    loan.pk,
                    request.user,
                    remarks,
                )

                messages.success(
                    request,
                    "Loan application rejected successfully.",
                )

            else:
                messages.error(
                    request,
                    "Invalid application decision.",
                )

        except BankError as error:
            messages.error(
                request,
                str(error),
            )

        return redirect(
            "loan_application_detail",
            loan_id=loan.pk,
        )

    client = loan.client

    eligibility = (
        loan.eligibility_checks
        .order_by("-checked_at")
        .first()
    )

    rule = LoanRule.objects.filter(
        product=loan.product,
    ).first()

    max_installment_ratio = (
        rule.max_installment_ratio
        if rule
        else Decimal("0.40")
    )

    min_savings_ratio = (
        rule.min_savings_ratio
        if rule
        else Decimal("0.10")
    )

    minimum_income = (
        rule.minimum_monthly_income
        if rule
        else Decimal("0.00")
    )

    minimum_age = (
        rule.minimum_age
        if rule
        else 18
    )

    minimum_credit_score = (
        rule.minimum_credit_score
        if rule
        else 0
    )

    schedule = build_schedule(
        loan.principal,
        loan.annual_rate,
        loan.term_months,
        timezone.localdate(),
    )

    proposed_installment = (
        max(
            (
                row["principal_due"] + row["interest_due"]
                for row in schedule
            ),
            default=Decimal("0.00"),
        )
    )

    monthly_income = client.monthly_income or Decimal("0.00")
    credit_score = client.credit_score or 0

    savings_balance = (
        SavingsAccount.objects.filter(
            client=client,
            status=SavingsAccount.Status.ACTIVE,
        )
        .aggregate(total=Sum("balance"))["total"]
        or Decimal("0.00")
    )

    required_savings = loan.principal * min_savings_ratio
    income_limit = monthly_income * max_installment_ratio

    age = None

    if client.date_of_birth:
        today = timezone.localdate()
        age = today.year - client.date_of_birth.year

        if (today.month, today.day) < (
            client.date_of_birth.month,
            client.date_of_birth.day,
        ):
            age -= 1

    criteria = []

    criteria.append({
        "label": "Minimum age",
        "detail": (
            f"Applicant age: {age} years; required: "
            f"{minimum_age} years."
            if age is not None
            else "Date of birth is missing."
        ),
        "passed": age is not None and age >= minimum_age,
        "review": age is None,
    })

    criteria.append({
        "label": "Minimum monthly income",
        "detail": (
            f"Monthly income: ₱{monthly_income:,.2f}; "
            f"required: ₱{minimum_income:,.2f}."
        ),
        "passed": monthly_income >= minimum_income,
        "review": False,
    })

    criteria.append({
        "label": "Installment affordability",
        "detail": (
            f"Proposed installment: ₱{proposed_installment:,.2f}; "
            f"maximum allowed: ₱{income_limit:,.2f} "
            f"({max_installment_ratio:.0%} of monthly income)."
        ),
        "passed": (
            monthly_income > 0
            and proposed_installment <= income_limit
        ),
        "review": monthly_income <= 0,
    })

    criteria.append({
        "label": "Savings requirement",
        "detail": (
            f"Active savings balance: ₱{savings_balance:,.2f}; "
            f"required: ₱{required_savings:,.2f}."
        ),
        "passed": savings_balance >= required_savings,
        "review": False,
    })

    criteria.append({
        "label": "Minimum credit score",
        "detail": (
            f"Credit score: {credit_score}; "
            f"required: {minimum_credit_score}."
        ),
        "passed": (
            credit_score >= minimum_credit_score
            and (
                minimum_credit_score == 0
                or credit_score > 0
            )
        ),
        "review": (
            minimum_credit_score > 0
            and credit_score <= 0
        ),
    })

    documents = loan.documents.order_by("-uploaded_at")

    context = {
        "loan": loan,
        "client": client,
        "eligibility": eligibility,
        "criteria": criteria,
        "documents": documents,
        "applicant_name": (
            client.user.get_full_name()
            or client.user.username
        ),
        "applicant_email": client.user.email,
        "applicant_phone": client.phone,
        "applicant_address": client.address,
        "employment_status": client.employment_status,
        "source_of_income": client.source_of_income,
        "monthly_income": monthly_income,
        "credit_score": credit_score,
        "age": age,
        "proposed_installment": proposed_installment,
        "savings_balance": savings_balance,
        "required_savings": required_savings,
        "income_limit": income_limit,
        "minimum_income": minimum_income,
        "minimum_age": minimum_age,
        "minimum_credit_score": minimum_credit_score,
        "max_installment_ratio": max_installment_ratio,
        "min_savings_ratio": min_savings_ratio,
    }

    return render(
        request,
        "officer/application_detail.html",
        context,
    )


@role_required("loan_officer", "admin")
def officer_loan_detail(request):
    return render(request, "officer/loan_detail.html")


# ---------- admin ----------

@role_required("admin")
def admin_users(request):
    users = (
        User.objects.select_related("role")
        .filter(
            role__name__in=[
                Role.ADMIN,
                Role.STAFF,
                Role.LOAN_OFFICER,
            ]
        )
        .order_by("username")
    )

    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )

    if role_filter in (
        Role.ADMIN,
        Role.STAFF,
        Role.LOAN_OFFICER,
    ):
        users = users.filter(role__name=role_filter)

    if status_filter == "active":
        users = users.filter(is_active=True)
    elif status_filter == "inactive":
        users = users.filter(is_active=False)

    context = {
        "users": users[:200],
        "q": q,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "roles": [
            (Role.ADMIN, "Admin"),
            (Role.STAFF, "Staff"),
            (Role.LOAN_OFFICER, "Loan Officer"),
        ],
    }

    return render(
        request,
        "adminpanel/users.html",
        context,
    )


@role_required("admin")
def admin_create_user(request):
    form = EmployeeUserCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        log(request.user, "create_employee_user", user)

        messages.success(
            request,
            f"Employee account '{user.username}' created successfully.",
        )

        return redirect("admin_users")

    return render(
        request,
        "adminpanel/user_form.html",
        {
            "form": form,
            "editing": False,
        },
    )


@role_required("admin")
def admin_edit_user(request, user_id):
    employee_roles = [
        Role.ADMIN,
        Role.STAFF,
        Role.LOAN_OFFICER,
    ]

    user = get_object_or_404(
        User.objects.select_related("role"),
        pk=user_id,
        role__name__in=employee_roles,
    )

    form = EmployeeUserEditForm(
        request.POST or None,
        instance=user,
    )

    if request.method == "POST" and form.is_valid():
        selected_role = form.cleaned_data["role"]

        if (
            user.pk == request.user.pk
            and selected_role.name != Role.ADMIN
        ):
            messages.error(
                request,
                "You cannot remove your own administrator role.",
            )
        else:
            form.save()
            log(request.user, "edit_employee_user", user)

            messages.success(
                request,
                f"Account '{user.username}' updated successfully.",
            )

            return redirect("admin_users")

    return render(
        request,
        "adminpanel/user_form.html",
        {
            "form": form,
            "editing": True,
            "target_user": user,
        },
    )


@role_required("admin")
def admin_toggle_user_status(request, user_id):
    if request.method != "POST":
        return redirect("admin_users")

    employee_roles = [
        Role.ADMIN,
        Role.STAFF,
        Role.LOAN_OFFICER,
    ]

    with transaction.atomic():
        user = get_object_or_404(
            User.objects.select_for_update().select_related("role"),
            pk=user_id,
            role__name__in=employee_roles,
        )

        if user.pk == request.user.pk:
            messages.error(
                request,
                "You cannot deactivate your own account.",
            )
            return redirect("admin_users")

        if user.is_active:
            if user.role.name == Role.ADMIN:
                active_admin_count = User.objects.filter(
                    role__name=Role.ADMIN,
                    is_active=True,
                ).count()

                if active_admin_count <= 1:
                    messages.error(
                        request,
                        "You cannot deactivate the last active administrator.",
                    )
                    return redirect("admin_users")

            user.is_active = False
            action = "deactivate_employee_user"
            status_message = "deactivated"

        else:
            user.is_active = True
            action = "reactivate_employee_user"
            status_message = "reactivated"

        user.save(update_fields=["is_active"])
        log(request.user, action, user)

    messages.success(
        request,
        f"Account '{user.username}' {status_message} successfully.",
    )

    return redirect("admin_users")


@role_required("admin")
def admin_clients(request):
    clients = (
        Client.objects.select_related("user")
        .order_by("-created_at")
    )

    status = request.GET.get("status", "")

    if status in Client.VerificationStatus.values:
        clients = clients.filter(verification_status=status)

    q = request.GET.get("q", "").strip()

    if q:
        clients = clients.filter(
            Q(user__username__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )

    return render(
        request,
        "adminpanel/clients.html",
        {
            "clients": clients[:200],
            "status": status,
            "q": q,
            "statuses": Client.VerificationStatus.choices,
        },
    )


@role_required("admin")
def admin_loan_products(request):
    return render(
        request,
        "adminpanel/loan_products.html",
        {
            "products": LoanProduct.objects.order_by("name"),
        },
    )


@role_required("admin")
def admin_product_form(request):
    return _demo_form(
        request,
        "adminpanel/product_form.html",
        "admin_loan_products",
    )


@role_required("admin")
def _parse_report_dates(request):
    today = timezone.localdate()
    default_from = today.replace(day=1)

    date_from_raw = request.GET.get("date_from", "").strip()
    date_to_raw = request.GET.get("date_to", "").strip()

    try:
        date_from = (
            date.fromisoformat(date_from_raw)
            if date_from_raw
            else default_from
        )
        date_to = (
            date.fromisoformat(date_to_raw)
            if date_to_raw
            else today
        )
    except ValueError:
        date_from = default_from
        date_to = today
        messages.error(
            request,
            "Invalid date filter. The current month's date range was used.",
        )

    if date_from > date_to:
        date_from = default_from
        date_to = today
        messages.error(
            request,
            "The starting date cannot be later than the ending date.",
        )

    return date_from, date_to


def _month_range(date_from, date_to):
    current = date(date_from.year, date_from.month, 1)
    last = date(date_to.year, date_to.month, 1)

    months = []

    while current <= last:
        months.append(current)

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return months


def _add_monthly_amount(target, transaction_date, amount):
    if not transaction_date:
        return

    month_key = date(
        transaction_date.year,
        transaction_date.month,
        1,
    )

    target[month_key] += amount or Decimal("0.00")


def _build_management_report(date_from, date_to):
    zero = Decimal("0.00")
    months = _month_range(date_from, date_to)

    # -------------------------------------------------
    # Actual transaction records within the date range
    # -------------------------------------------------

    interest_entries = LedgerEntry.objects.filter(
        entry_type=LedgerEntry.EntryType.INTEREST_CREDIT,
        savings_account__isnull=False,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )

    loan_payments = LoanPayment.objects.filter(
        payment_date__date__gte=date_from,
        payment_date__date__lte=date_to,
    )

    disbursements = Disbursement.objects.filter(
        disbursed_at__date__gte=date_from,
        disbursed_at__date__lte=date_to,
    )

    savings_entries = LedgerEntry.objects.filter(
        savings_account__isnull=False,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
        entry_type__in=[
            LedgerEntry.EntryType.DEPOSIT,
            LedgerEntry.EntryType.WITHDRAWAL,
        ],
    )

    total_interest = (
        interest_entries.aggregate(total=Sum("amount"))["total"]
        or zero
    )

    total_repayments = (
        loan_payments.aggregate(total=Sum("amount"))["total"]
        or zero
    )

    total_disbursements = (
        disbursements.aggregate(total=Sum("amount"))["total"]
        or zero
    )

    total_savings_deposits = (
        savings_entries.filter(
            entry_type=LedgerEntry.EntryType.DEPOSIT,
        ).aggregate(total=Sum("amount"))["total"]
        or zero
    )

    total_savings_withdrawals = (
        savings_entries.filter(
            entry_type=LedgerEntry.EntryType.WITHDRAWAL,
        ).aggregate(total=Sum("amount"))["total"]
        or zero
    )

    # -------------------------------------------------
    # Loan portfolio snapshot
    # -------------------------------------------------

    active_loans = Loan.objects.filter(
        status=Loan.Status.ACTIVE,
    )

    active_loan_count = active_loans.count()

    active_installments = Installment.objects.filter(
        loan__status=Loan.Status.ACTIVE,
    ).exclude(
        status=Installment.Status.PAID,
    ).select_related("loan")

    outstanding_scheduled_balance = zero

    for installment in active_installments:
        remaining = installment.total_due - installment.amount_paid

        if remaining > zero:
            outstanding_scheduled_balance += remaining

    # -------------------------------------------------
    # Delinquent loan snapshot
    # An installment is overdue if its due date is
    # earlier than the selected ending date and it
    # has not been fully paid.
    # -------------------------------------------------

    overdue_installments = (
        Installment.objects.filter(
            due_date__lt=date_to,
        )
        .exclude(status=Installment.Status.PAID)
        .select_related("loan")
    )

    delinquent_loan_ids = set()
    overdue_amount = zero

    for installment in overdue_installments:
        remaining = installment.total_due - installment.amount_paid

        if remaining > zero:
            delinquent_loan_ids.add(installment.loan_id)
            overdue_amount += remaining

    delinquent_loan_count = len(delinquent_loan_ids)

    # -------------------------------------------------
    # Loan status distribution
    # -------------------------------------------------

    loan_status_counts = {
        status: 0
        for status, label in Loan.Status.choices
    }

    status_rows = (
        Loan.objects.values("status")
        .annotate(total=Count("id"))
    )

    for row in status_rows:
        loan_status_counts[row["status"]] = row["total"]

    loan_status_labels = [
        label
        for status, label in Loan.Status.choices
    ]

    loan_status_values = [
        loan_status_counts[status]
        for status, label in Loan.Status.choices
    ]

    # -------------------------------------------------
    # Monthly activity
    # -------------------------------------------------

    monthly_interest = defaultdict(lambda: zero)
    monthly_repayments = defaultdict(lambda: zero)
    monthly_disbursements = defaultdict(lambda: zero)
    monthly_savings_deposits = defaultdict(lambda: zero)
    monthly_savings_withdrawals = defaultdict(lambda: zero)

    for entry in interest_entries:
        _add_monthly_amount(
            monthly_interest,
            entry.created_at,
            entry.amount,
        )

    for payment in loan_payments:
        _add_monthly_amount(
            monthly_repayments,
            payment.payment_date,
            payment.amount,
        )

    for disbursement in disbursements:
        _add_monthly_amount(
            monthly_disbursements,
            disbursement.disbursed_at,
            disbursement.amount,
        )

    for entry in savings_entries:
        if entry.entry_type == LedgerEntry.EntryType.DEPOSIT:
            _add_monthly_amount(
                monthly_savings_deposits,
                entry.created_at,
                entry.amount,
            )

        elif entry.entry_type == LedgerEntry.EntryType.WITHDRAWAL:
            _add_monthly_amount(
                monthly_savings_withdrawals,
                entry.created_at,
                entry.amount,
            )

    month_labels = [
        month.strftime("%b %Y")
        for month in months
    ]

    monthly_rows = []

    for month in months:
        monthly_rows.append({
            "month": month.strftime("%b %Y"),
            "interest": monthly_interest[month],
            "repayments": monthly_repayments[month],
            "disbursements": monthly_disbursements[month],
            "savings_deposits": monthly_savings_deposits[month],
            "savings_withdrawals": monthly_savings_withdrawals[month],
        })

    # Chart.js receives numeric values.
    chart_data = {
        "loan_status": {
            "labels": loan_status_labels,
            "values": loan_status_values,
        },
        "loan_activity": {
            "labels": month_labels,
            "disbursements": [
                float(monthly_disbursements[month])
                for month in months
            ],
            "repayments": [
                float(monthly_repayments[month])
                for month in months
            ],
        },
        "savings_activity": {
            "labels": month_labels,
            "deposits": [
                float(monthly_savings_deposits[month])
                for month in months
            ],
            "withdrawals": [
                float(monthly_savings_withdrawals[month])
                for month in months
            ],
        },
        "interest_activity": {
            "labels": month_labels,
            "interest": [
                float(monthly_interest[month])
                for month in months
            ],
        },
    }

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_interest": total_interest,
        "total_repayments": total_repayments,
        "total_disbursements": total_disbursements,
        "total_savings_deposits": total_savings_deposits,
        "total_savings_withdrawals": total_savings_withdrawals,
        "active_loan_count": active_loan_count,
        "outstanding_scheduled_balance": outstanding_scheduled_balance,
        "delinquent_loan_count": delinquent_loan_count,
        "overdue_amount": overdue_amount,
        "loan_status_counts": loan_status_counts,
        "loan_status_labels": loan_status_labels,
        "loan_status_values": loan_status_values,
        "monthly_rows": monthly_rows,
        "chart_data": chart_data,
    }


def _export_management_report_excel(report):
    workbook = Workbook()

    summary = workbook.active
    summary.title = "Management Summary"

    summary.append(["BAYAN BANK - MANAGEMENT REPORT"])
    summary.append([
        "Reporting period",
        f"{report['date_from']} to {report['date_to']}",
    ])
    summary.append([])
    summary.append(["Metric", "Actual Amount / Count"])

    summary_data = [
        ("Savings interest credited", report["total_interest"]),
        ("Loan repayments collected", report["total_repayments"]),
        ("Loan disbursements", report["total_disbursements"]),
        ("Savings deposits", report["total_savings_deposits"]),
        ("Savings withdrawals", report["total_savings_withdrawals"]),
        ("Active loans", report["active_loan_count"]),
        (
            "Remaining scheduled balance of active loans",
            report["outstanding_scheduled_balance"],
        ),
        ("Delinquent loans", report["delinquent_loan_count"]),
        ("Overdue installment balance", report["overdue_amount"]),
    ]

    for row in summary_data:
        summary.append(list(row))

    summary["A1"].font = Font(
        bold=True,
        size=16,
        color="FFFFFF",
    )
    summary["A1"].fill = PatternFill(
        "solid",
        fgColor="17365D",
    )

    for cell in summary[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            "solid",
            fgColor="1F4E78",
        )

    for row in summary.iter_rows(min_row=5, min_col=2, max_col=2):
        if isinstance(row[0].value, Decimal):
            row[0].number_format = '"₱"#,##0.00'

    summary.column_dimensions["A"].width = 48
    summary.column_dimensions["B"].width = 28

    status_sheet = workbook.create_sheet("Loan Status")

    status_sheet.append(["Loan Status", "Number of Loans"])

    for status, label in Loan.Status.choices:
        status_sheet.append([
            label,
            report["loan_status_counts"].get(status, 0),
        ])

    for cell in status_sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            "solid",
            fgColor="1F4E78",
        )

    status_sheet.column_dimensions["A"].width = 25
    status_sheet.column_dimensions["B"].width = 20

    activity = workbook.create_sheet("Monthly Activity")

    activity.append([
        "Month",
        "Interest Credited",
        "Loan Repayments",
        "Loan Disbursements",
        "Savings Deposits",
        "Savings Withdrawals",
    ])

    for row in report["monthly_rows"]:
        activity.append([
            row["month"],
            float(row["interest"]),
            float(row["repayments"]),
            float(row["disbursements"]),
            float(row["savings_deposits"]),
            float(row["savings_withdrawals"]),
        ])

    for cell in activity[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            "solid",
            fgColor="1F4E78",
        )
        cell.alignment = Alignment(
            horizontal="center",
        )

    for column in activity.columns:
        activity.column_dimensions[
            column[0].column_letter
        ].width = 24

    for row in activity.iter_rows(
        min_row=2,
        min_col=2,
    ):
        for cell in row:
            cell.number_format = '"₱"#,##0.00'

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        'attachment; filename="bayan_bank_management_report.xlsx"'
    )

    return response


def _export_management_report_pdf(report):
    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
    )

    elements = [
        Paragraph(
            "BAYAN BANK",
            title_style,
        ),
        Paragraph(
            "Management Reports",
            styles["Heading2"],
        ),
        Paragraph(
            (
                f"Reporting period: {report['date_from']} "
                f"to {report['date_to']}"
            ),
            styles["Normal"],
        ),
        Spacer(1, 16),
        Paragraph(
            "Financial and Transaction Activity",
            styles["Heading2"],
        ),
    ]

    summary_rows = [
        ["Metric", "Actual Amount / Count"],
        ["Savings interest credited", f"PHP {report['total_interest']:,.2f}"],
        ["Loan repayments collected", f"PHP {report['total_repayments']:,.2f}"],
        ["Loan disbursements", f"PHP {report['total_disbursements']:,.2f}"],
        ["Savings deposits", f"PHP {report['total_savings_deposits']:,.2f}"],
        ["Savings withdrawals", f"PHP {report['total_savings_withdrawals']:,.2f}"],
        ["Active loans", str(report["active_loan_count"])],
        [
            "Remaining scheduled balance of active loans",
            f"PHP {report['outstanding_scheduled_balance']:,.2f}",
        ],
        ["Delinquent loans", str(report["delinquent_loan_count"])],
        [
            "Overdue installment balance",
            f"PHP {report['overdue_amount']:,.2f}",
        ],
    ]

    summary_table = Table(
        summary_rows,
        colWidths=[3.8 * inch, 2.5 * inch],
        repeatRows=1,
    )

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#F2F5F9"),
        ]),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))

    elements.extend([
        summary_table,
        Spacer(1, 18),
        Paragraph(
            "Loan Status Distribution",
            styles["Heading2"],
        ),
    ])

    status_rows = [["Loan Status", "Number of Loans"]]

    for status, label in Loan.Status.choices:
        status_rows.append([
            label,
            str(report["loan_status_counts"].get(status, 0)),
        ])

    status_table = Table(
        status_rows,
        colWidths=[3.8 * inch, 2.5 * inch],
        repeatRows=1,
    )

    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))

    elements.extend([
        status_table,
        Spacer(1, 18),
        Paragraph(
            "Monthly Activity",
            styles["Heading2"],
        ),
    ])

    monthly_rows = [[
        "Month",
        "Interest",
        "Repayments",
        "Disbursements",
        "Savings Deposits",
        "Savings Withdrawals",
    ]]

    for row in report["monthly_rows"]:
        monthly_rows.append([
            row["month"],
            f"{row['interest']:,.2f}",
            f"{row['repayments']:,.2f}",
            f"{row['disbursements']:,.2f}",
            f"{row['savings_deposits']:,.2f}",
            f"{row['savings_withdrawals']:,.2f}",
        ])

    monthly_table = Table(
        monthly_rows,
        repeatRows=1,
    )

    monthly_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))

    elements.extend([
        monthly_table,
        Spacer(1, 14),
        Paragraph(
            (
                "Note: Loan repayments and savings deposits are "
                "transaction activity, not automatically accounting "
                "income. Loan disbursements and savings withdrawals "
                "are not automatically accounting expenses. "
                "The remaining scheduled loan balance includes "
                "unpaid scheduled principal, interest, and penalties; "
                "it is not a principal-only balance."
            ),
            styles["Italic"],
        ),
    ])

    document.build(elements)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        'attachment; filename="bayan_bank_management_report.pdf"'
    )

    return response


@role_required("admin")
def admin_reports(request):
    date_from, date_to = _parse_report_dates(request)

    report = _build_management_report(
        date_from,
        date_to,
    )

    export_type = request.GET.get("export", "").lower()

    if export_type == "pdf":
        return _export_management_report_pdf(report)

    if export_type == "excel":
        return _export_management_report_excel(report)

    context = {
        **report,
        "date_from_value": date_from.isoformat(),
        "date_to_value": date_to.isoformat(),
        "chart_data_json": report["chart_data"],
    }

    return render(
        request,
        "adminpanel/reports.html",
        context,
    )

@role_required("admin")
def admin_audit_log(request):
    audit_logs = (
        AuditLog.objects.select_related("user", "user__role")
        .all()
        .order_by("-created_at", "-id")
    )

    username = request.GET.get("user", "").strip()
    action = request.GET.get("action", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if username:
        audit_logs = audit_logs.filter(
            Q(user__username__icontains=username)
            | Q(user__first_name__icontains=username)
            | Q(user__last_name__icontains=username)
        )

    if action:
        audit_logs = audit_logs.filter(action__icontains=action)

    if date_from:
        audit_logs = audit_logs.filter(
            created_at__date__gte=date_from
        )

    if date_to:
        audit_logs = audit_logs.filter(
            created_at__date__lte=date_to
        )

    if request.GET.get("export") == "1":
        response = HttpResponse(
            content_type="text/csv; charset=utf-8"
        )

        response["Content-Disposition"] = (
            'attachment; filename="bayan_bank_audit_logs.csv"'
        )

        writer = csv.writer(response)

        writer.writerow([
            "Date and Time",
            "Username",
            "Role",
            "Action",
            "Object Type",
            "Object ID",
            "Details",
            "IP Address",
        ])

        for entry in audit_logs:
            user = entry.user

            role_name = (
                user.role.name
                if user and getattr(user, "role", None)
                else "Unknown"
            )

            writer.writerow([
                timezone.localtime(entry.created_at).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                user.username if user else "System",
                role_name,
                entry.action,
                entry.object_type,
                entry.object_id,
                entry.details,
                entry.ip_address or "",
            ])

        return response

    context = {
        "audit_logs": audit_logs[:500],
        "filter_user": username,
        "filter_action": action,
        "date_from": date_from,
        "date_to": date_to,
    }

    return render(
        request,
        "adminpanel/audit_log.html",
        context,
    )


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)