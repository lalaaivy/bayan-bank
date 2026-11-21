
from django.urls import path

from . import views

urlpatterns = [
    # Client portal
    path(
        "portal/savings/",
        views.portal_savings,
        name="portal_savings",
    ),
    path(
        "portal/savings/open/",
        views.portal_open_account,
        name="portal_open_account",
    ),
    path(
        "portal/savings/transfer/",
        views.portal_transfer,
        name="portal_transfer",
    ),
    path(
        "portal/savings/deposits/<int:deposit_id>/release/",
        views.portal_release_matured,
        name="portal_release_matured",
    ),
    path(
        "portal/savings/deposits/<int:deposit_id>/early-withdrawal/",
        views.portal_request_early_withdrawal,
        name="portal_request_early_withdrawal",
    ),

    # Staff and admin savings accounts
    path(
        "staff/savings/accounts/",
        views.staff_savings,
        name="staff_savings_accounts",
    ),
    path(
        "staff/savings/<int:account_id>/",
        views.staff_account,
        name="staff_account",
    ),
    path(
        "staff/savings/<int:account_id>/deposit/",
        views.staff_deposit,
        name="staff_deposit",
    ),
    path(
        "staff/savings/<int:account_id>/withdraw/",
        views.staff_withdraw,
        name="staff_withdraw",
    ),
    path(
        "staff/savings/<int:account_id>/interest/",
        views.staff_post_interest,
        name="staff_post_interest",
    ),
    path(
        "staff/savings/withdrawal-requests/<int:request_id>/approve/",
        views.staff_approve_early_withdrawal,
        name="staff_approve_early_withdrawal",
    ),
    path(
        "staff/savings/withdrawal-requests/<int:request_id>/reject/",
        views.staff_reject_early_withdrawal,
        name="staff_reject_early_withdrawal",
    ),
]
