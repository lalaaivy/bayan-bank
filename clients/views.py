
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from accounts.decorators import role_required
from loans.models import Loan
from savings.models import SavingsAccount

from .models import Client


@role_required("admin", "staff", "loan_officer")
def staff_clients(request):
    clients = Client.objects.select_related("user").order_by("-created_at")

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

    return render(
        request,
        "staff/client_detail.html",
        {
            "client": client,
            "savings_accounts": savings_accounts,
            "loans": loans,
        },
    )
