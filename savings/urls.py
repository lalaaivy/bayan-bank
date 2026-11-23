
from django.urls import path

from accounts.sod import action_roles

from . import views


urlpatterns = [

    # ==========================================
    # CLIENT SAVINGS PORTAL
    # ==========================================

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

    # ==========================================
    # SAVINGS ACCOUNT MANAGEMENT
    # Existing view-level role restrictions
    # remain active.
    # ==========================================

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

    # ==========================================
    # SAVINGS DEPOSITS
    # Staff only
    # ==========================================

    path(
        "staff/savings/<int:account_id>/deposit/",
        action_roles("staff")(
            views.staff_deposit
        ),
        name="staff_deposit",
    ),

    # ==========================================
    # SAVINGS WITHDRAWALS
    # Staff only
    # ==========================================

    path(
        "staff/savings/<int:account_id>/withdraw/",
        action_roles("staff")(
            views.staff_withdraw
        ),
        name="staff_withdraw",
    ),

    # ==========================================
    # SAVINGS INTEREST POSTING
    # Staff only
    # ==========================================

    path(
        "staff/savings/<int:account_id>/interest/",
        action_roles("staff")(
            views.staff_post_interest
        ),
        name="staff_post_interest",
    ),

    # ==========================================
    # EARLY WITHDRAWAL APPROVAL
    # Staff only
    # ==========================================

    path(
        "staff/savings/withdrawal-requests/<int:request_id>/approve/",
        action_roles("staff")(
            views.staff_approve_early_withdrawal
        ),
        name="staff_approve_early_withdrawal",
    ),

    # ==========================================
    # EARLY WITHDRAWAL REJECTION
    # Staff only
    # ==========================================

    path(
        "staff/savings/withdrawal-requests/<int:request_id>/reject/",
        action_roles("staff")(
            views.staff_reject_early_withdrawal
        ),
        name="staff_reject_early_withdrawal",
    ),
]
