
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.services import log
from clients.models import Client, ClientDocument
from loans.models import Loan, LoanProduct
from notifications.models import Notification
from savings.models import SavingsAccount

from .decorators import client_required, role_required
from .forms import (
    ClientDocumentForm,
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
    accounts = SavingsAccount.objects.filter(client=request.client)
    balance = accounts.aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
    loans = (
        Loan.objects.filter(client=request.client)
        .select_related("product")
        .order_by("-applied_at")
    )
    latest_document = request.client.documents.order_by("-uploaded_at").first()

    context = {
        "balance": balance,
        "accounts": accounts,
        "loans": loans,
        "client": request.client,
        "latest_document": latest_document,
    }
    return render(request, "portal/home.html", context)


@role_required("staff", "admin", "loan_officer")
def staff_home(request):
    context = {
        "pending_count": Loan.objects.filter(status=Loan.Status.PENDING).count(),
        "active_count": Loan.objects.filter(status=Loan.Status.ACTIVE).count(),
    }
    return render(request, "staff/home.html", context)


@role_required("loan_officer", "admin")
def officer_home(request):
    return render(request, "officer/home.html")


@role_required("admin")
def admin_home(request):
    return render(request, "adminpanel/home.html")


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


@role_required("client")
def client_profile(request):
    return render(request, "portal/profile.html")


@role_required("client")
def edit_client_profile(request):
    return _demo_form(
        request,
        "portal/profile_edit.html",
        "client_profile",
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
    return render(request, "staff/clients.html")


@role_required("staff", "admin")
def staff_add_client(request):
    return _demo_form(
        request,
        "staff/add_client.html",
        "staff_clients",
    )


@role_required("staff", "admin")
def staff_client_detail(request):
    return render(request, "staff/client_detail.html")


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

        is_pending = (
            client.verification_status
            == Client.VerificationStatus.PENDING
        )

        if decision not in ("approve", "reject"):
            messages.error(request, "Please choose Approve or Reject.")

        elif not is_pending:
            messages.error(
                request,
                "This client is no longer pending verification.",
            )

        elif decision == "approve" and document is None:
            messages.error(
                request,
                "Cannot approve: this client has not uploaded an ID yet.",
            )

        else:
            approved = decision == "approve"

            client.verification_status = (
                Client.VerificationStatus.ACTIVE
                if approved
                else Client.VerificationStatus.REJECTED
            )
            client.verified_by = request.user
            client.verified_at = timezone.now()

            client.save(
                update_fields=[
                    "verification_status",
                    "verified_by",
                    "verified_at",
                ]
            )

            if document is not None:
                document.status = (
                    ClientDocument.Status.VERIFIED
                    if approved
                    else ClientDocument.Status.REJECTED
                )
                document.reviewed_by = request.user
                document.reviewed_at = timezone.now()
                document.remark = request.POST.get(
                    "remark",
                    "",
                ).strip()[:255]

                document.save(
                    update_fields=[
                        "status",
                        "reviewed_by",
                        "reviewed_at",
                        "remark",
                    ]
                )

            log(request.user, f"{decision}_client", client)

            result = "approved" if approved else "rejected"
            messages.success(
                request,
                f"{client.client_code} {result}.",
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


@role_required("staff", "admin")
def release_loans(request):
    return render(request, "staff/release_loan.html")


@role_required("staff", "admin")
def confirm_loan_release(request):
    return _demo_form(
        request,
        "staff/release_confirmation.html",
        "release_loans",
    )


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
    return render(request, "officer/loans.html")


@role_required("loan_officer", "admin")
def loan_application_detail(request):
    return _demo_form(
        request,
        "officer/application_detail.html",
        "loan_applications",
    )


@role_required("loan_officer", "admin")
def officer_loan_detail(request):
    return render(request, "officer/loan_detail.html")


# ---------- admin ----------

@role_required("admin")
def admin_users(request):
    users = (
        User.objects.select_related("role")
        .filter(role__name__in=[
            Role.ADMIN,
            Role.STAFF,
            Role.LOAN_OFFICER,
        ])
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
def admin_reports(request):
    if request.GET.get("export") in {"pdf", "excel"}:
        messages.info(request, "Export coming soon")
        return redirect("admin_reports")

    return render(request, "adminpanel/reports.html")


@role_required("admin")
def admin_audit_log(request):
    if request.GET.get("export"):
        messages.info(request, "Export coming soon")
        return redirect("admin_audit_log")

    return render(request, "adminpanel/audit_log.html")


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
