from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounting.models import BankAccount
from audit.services import log
from loans.models import Loan
from savings.models import SavingsAccount

from .models import (
    Client,
    ClientDocument,
    ReactivationRequest,
    SecurityFreeze,
)
from .services import (
    freeze_client,
    release_security_freeze,
    review_reactivation_request,
    submit_reactivation_request,
)
from django.contrib.auth import get_user_model


# --------------------------------------------------
# STAFF CLIENT LIST
# --------------------------------------------------

@role_required("admin", "staff", "loan_officer")
def staff_clients(request):
    clients = Client.objects.select_related(
        "user"
    ).order_by("-created_at")

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        clients = clients.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(phone__icontains=search)
        )

    valid_statuses = [
        choice.value for choice in Client.VerificationStatus
    ]

    if status in valid_statuses:
        clients = clients.filter(verification_status=status)

    return render(
        request,
        "staff/clients.html",
        {
            "clients": clients,
            "search": search,
            "selected_status": status,
            "status_choices": Client.VerificationStatus.choices,
        },
    )


# --------------------------------------------------
# STAFF CLIENT DETAIL
# --------------------------------------------------

@role_required("admin", "staff", "loan_officer")
def staff_client_detail(request, client_id):
    client = get_object_or_404(
        Client.objects.select_related("user", "verified_by"),
        pk=client_id,
    )

    savings_accounts = SavingsAccount.objects.filter(
        client=client
    ).order_by("account_number")

    loans = Loan.objects.filter(
        client=client
    ).select_related("product").order_by("-applied_at")

    security_freezes = SecurityFreeze.objects.filter(
        client=client
    ).select_related(
        "frozen_by",
        "unfrozen_by",
    ).order_by("-started_at")

    return render(
        request,
        "staff/client_detail.html",
        {
            "client": client,
            "savings_accounts": savings_accounts,
            "loans": loans,
            "security_freezes": security_freezes,
            "active_security_freeze": security_freezes.filter(
                status=SecurityFreeze.Status.ACTIVE
            ).first(),
        },
    )


# --------------------------------------------------
# CLIENT SELF-DEACTIVATION
# --------------------------------------------------

# --------------------------------------------------
# CLIENT SELF-DEACTIVATION
# --------------------------------------------------

@login_required
@role_required("client")
@require_POST
def client_deactivate(request):
    """
    Allow a client to deactivate their own login.

    This does not delete their client profile, accounts,
    loans, transactions, or financial history.
    """
    User = get_user_model()

    client = get_object_or_404(
        Client.objects.select_related("user"),
        user=request.user,
    )

    with transaction.atomic():
        user = User.objects.select_for_update().get(
            pk=request.user.pk
        )

        if not user.is_active:
            messages.info(
                request,
                "Your login is already deactivated.",
            )
            return redirect("portal_home")

        user.is_active = False
        user.save(update_fields=["is_active"])

        log(
            user,
            "CLIENT_SELF_DEACTIVATED",
            obj=client,
            ip=request.META.get("REMOTE_ADDR"),
            reason="Client requested account deactivation.",
        )

    logout(request)

    return render(
        request,
        "clients/deactivated.html",
        {
            "client": client,
            "self_deactivated": True,
        },
    )


# --------------------------------------------------
# ADMIN CLIENT DEACTIVATION
# --------------------------------------------------

@login_required
@role_required("admin")
@require_POST
def admin_deactivate_client(request, client_id):
    """
    Allow an administrator to deactivate a client's login.

    Financial records and the client profile are retained.
    """
    User = get_user_model()

    with transaction.atomic():
        client = get_object_or_404(
            Client.objects.select_for_update().select_related("user"),
            pk=client_id,
        )

        user = User.objects.select_for_update().get(
            pk=client.user_id
        )

        if not user.is_active:
            messages.info(
                request,
                "This client's login is already deactivated.",
            )
            return redirect(
                "staff_client_detail",
                client_id=client.pk,
            )

        user.is_active = False
        user.save(update_fields=["is_active"])

        log(
            request.user,
            "CLIENT_ADMIN_DEACTIVATED",
            obj=client,
            ip=request.META.get("REMOTE_ADDR"),
            reason=(
                request.POST.get("reason", "").strip()
                or "Administrator deactivated the client login."
            ),
        )

    messages.success(
        request,
        "Client login deactivated. Financial records were preserved.",
    )

    return redirect(
        "staff_client_detail",
        client_id=client.pk,
    )

# --------------------------------------------------
# ADMIN SAFE CLIENT DELETION
# --------------------------------------------------

@login_required
@role_required("admin")
@require_POST
def admin_delete_client(request, client_id):
    """
    Delete a client profile only when no protected records exist.

    The associated User account is retained and deactivated.
    Financial history is never deleted through this view.
    """
    try:
        with transaction.atomic():
            client = get_object_or_404(
                Client.objects.select_for_update().select_related("user"),
                pk=client_id,
            )

            confirmation = request.POST.get(
                "confirm_delete",
                "",
            ).strip()

            if confirmation != "DELETE":
                messages.error(
                    request,
                    "Deletion was not confirmed. No records were changed.",
                )
                return redirect(
                    "staff_client_detail",
                    client_id=client.pk,
                )

            has_bank_accounts = BankAccount.objects.filter(
                client=client
            ).exists()

            has_savings_accounts = SavingsAccount.objects.filter(
                client=client
            ).exists()

            has_loans = Loan.objects.filter(
                client=client
            ).exists()

            has_documents = ClientDocument.objects.filter(
                client=client
            ).exists()

            has_security_freezes = SecurityFreeze.objects.filter(
                client=client
            ).exists()

            has_reactivation_requests = ReactivationRequest.objects.filter(
                client=client
            ).exists()

            if any((
                has_bank_accounts,
                has_savings_accounts,
                has_loans,
                has_documents,
                has_security_freezes,
                has_reactivation_requests,
            )):
                messages.error(
                    request,
                    "This client cannot be deleted because related "
                    "accounts, financial records, documents, security "
                    "records, or reactivation requests exist. "
                    "Deactivate the login instead to preserve history.",
                )
                return redirect(
                    "staff_client_detail",
                    client_id=client.pk,
                )

            user = type(client.user).objects.select_for_update().get(
                pk=client.user_id
            )

            user.is_active = False
            user.save(update_fields=["is_active"])

            log(
                request.user,
                "CLIENT_PROFILE_DELETED",
                obj=client,
                ip=request.META.get("REMOTE_ADDR"),
                reason="Administrator deleted an eligible client profile.",
            )

            client.delete()

    except ProtectedError:
        messages.error(
            request,
            "Deletion was blocked because protected records still "
            "reference this client. No financial history was removed.",
        )
        return redirect("admin_clients")

    messages.success(
        request,
        "Client profile deleted. The associated login record was "
        "retained and deactivated.",
    )

    return redirect("admin_clients")


# --------------------------------------------------
# PUBLIC REACTIVATION REQUEST
# --------------------------------------------------

def public_reactivation_request(request):
    """
    Public page for clients whose login has been deactivated.

    The response does not disclose whether the submitted
    client ID and username matched an existing record.
    """

    if request.method == "POST":
        client_id = request.POST.get("client_id", "").strip()
        username = request.POST.get("username", "").strip()
        reason = request.POST.get("reason", "").strip()

        if (
            not client_id.isdigit()
            or not username
            or len(reason) < 10
        ):
            messages.error(
                request,
                "Please provide a valid Client ID, username, "
                "and a reason with at least 10 characters.",
            )
            return render(
                request,
                "clients/reactivation_request.html",
            )

        client = Client.objects.select_related("user").filter(
            pk=int(client_id),
            user__username__iexact=username,
            user__is_active=False,
        ).first()

        if client:
            try:
                submit_reactivation_request(
                    client_id=client.pk,
                    reason=reason,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return render(
                    request,
                    "clients/reactivation_request.html",
                )
            except PermissionDenied:
                messages.error(
                    request,
                    "Your request could not be processed. "
                    "Please contact a branch for assistance.",
                )
                return render(
                    request,
                    "clients/reactivation_request.html",
                )

        # Keep the response generic to avoid revealing
        # whether a Client ID and username match.
        messages.success(
            request,
            "If the information matches a deactivated client account, "
            "your request has been submitted for review. "
            "Please contact the branch if you need assistance.",
        )

        return redirect("public_reactivation_request")

    return render(
        request,
        "clients/reactivation_request.html",
    )

# --------------------------------------------------
# ADMIN REACTIVATION REQUEST QUEUE
# --------------------------------------------------

@login_required
@role_required("admin", "staff")
def admin_reactivation_requests(request):
    requests = (
        ReactivationRequest.objects
        .select_related(
            "client",
            "client__user",
            "reviewed_by",
        )
        .order_by("-requested_at")
    )

    status = request.GET.get("status", "").strip()

    if status in ReactivationRequest.Status.values:
        requests = requests.filter(status=status)

    return render(
        request,
        "adminpanel/reactivation_requests.html",
        {
            "requests": requests,
            "selected_status": status,
            "status_choices": ReactivationRequest.Status.choices,
        },
    )


# --------------------------------------------------
# REVIEW REACTIVATION REQUEST
# --------------------------------------------------

@login_required
@role_required("admin", "staff")
@require_POST
def admin_review_reactivation_request(request, request_id):
    reactivation = get_object_or_404(
        ReactivationRequest,
        pk=request_id,
    )

    decision = request.POST.get("decision", "").strip().lower()
    staff_notes = request.POST.get("staff_notes", "").strip()
    branch_reference = request.POST.get(
        "branch_reference",
        "",
    ).strip()

    if decision not in ("approve", "reject"):
        messages.error(request, "Invalid review decision.")
        return redirect("admin_reactivation_requests")

    try:
        review_reactivation_request(
            request_id=reactivation.pk,
            reviewed_by=request.user,
            approved=(decision == "approve"),
            staff_notes=staff_notes,
            branch_reference=branch_reference,
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect("admin_reactivation_requests")

    messages.success(
        request,
        "The reactivation request has been "
        f"{'approved' if decision == 'approve' else 'rejected'}.",
    )

    return redirect("admin_reactivation_requests")


# --------------------------------------------------
# ADMIN SECURITY FREEZE
# --------------------------------------------------

@login_required
@role_required("admin")
@require_POST
def admin_freeze_client(request, client_id):
    client = get_object_or_404(Client, pk=client_id)

    severity = request.POST.get("severity", "").strip().lower()
    reason = request.POST.get("reason", "").strip()

    try:
        freeze = freeze_client(
            client_id=client.pk,
            severity=severity,
            reason=reason,
            frozen_by=request.user,
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect(
            "staff_client_detail",
            client_id=client.pk,
        )

    if freeze.severity == SecurityFreeze.Severity.MINOR:
        messages.success(
            request,
            "Temporary security freeze applied. "
            "It is scheduled to expire after 24 hours.",
        )
    else:
        messages.success(
            request,
            "Serious security freeze applied. "
            "It requires branch verification and manual release.",
        )

    return redirect(
        "staff_client_detail",
        client_id=client.pk,
    )


# --------------------------------------------------
# RELEASE SECURITY FREEZE
# --------------------------------------------------

@login_required
@role_required("admin", "staff")
@require_POST
def admin_release_security_freeze(request, freeze_id):
    freeze = get_object_or_404(
        SecurityFreeze.objects.select_related("client"),
        pk=freeze_id,
    )

    branch_reference = request.POST.get(
        "branch_reference",
        "",
    ).strip()

    staff_notes = request.POST.get(
        "staff_notes",
        "",
    ).strip()

    try:
        release_security_freeze(
            freeze_id=freeze.pk,
            released_by=request.user,
            branch_reference=branch_reference,
            staff_notes=staff_notes,
        )
    except (ValueError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect(
            "staff_client_detail",
            client_id=freeze.client_id,
        )

    messages.success(
        request,
        "The security freeze has been released.",
    )

    return redirect(
        "staff_client_detail",
        client_id=freeze.client_id,
    )