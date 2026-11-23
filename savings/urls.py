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

    # Regular BankAccount -> SavingsAccount
    path(
        "portal/savings/transfer/",
        views.portal_transfer,
        name="portal_transfer",
    ),

    # Client requests physical cash withdrawal
    path(
        "portal/savings/deposits/<int:deposit_id>/cash-withdrawal/",
        views.portal_request_cash_withdrawal,
        name="portal_request_cash_withdrawal",
    ),

    # SavingsAccount matured deposit -> transfer request
    path(
        "portal/savings/deposits/<int:deposit_id>/transfer-request/",
        views.portal_request_savings_transfer,
        name="portal_request_savings_transfer",
    ),

    # Legacy URL retained for compatibility
    path(
        "portal/savings/deposits/<int:deposit_id>/release/",
        views.portal_release_matured,
        name="portal_release_matured",
    ),

    # Locked deposit early-withdrawal request
    path(
        "portal/savings/deposits/<int:deposit_id>/early-withdrawal/",
        views.portal_request_early_withdrawal,
        name="portal_request_early_withdrawal",
    ),

    # ==========================================
    # SAVINGS ACCOUNT MANAGEMENT
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
    # PHYSICAL SAVINGS DEPOSITS
    # ==========================================

    path(
        "staff/savings/<int:account_id>/deposit/",
        action_roles("staff")(views.staff_deposit),
        name="staff_deposit",
    ),

    # ==========================================
    # PHYSICAL SAVINGS WITHDRAWALS
    # ==========================================

    # Legacy staff withdrawal endpoint
    path(
        "staff/savings/<int:account_id>/withdraw/",
        action_roles("staff")(views.staff_withdraw),
        name="staff_withdraw",
    ),

    # Staff approves a client's physical cash withdrawal request
    path(
        "staff/savings/cash-withdrawal-requests/<int:request_id>/approve/",
        action_roles("staff")(views.staff_approve_cash_withdrawal),
        name="staff_approve_cash_withdrawal",
    ),

    # Staff rejects a client's physical cash withdrawal request
    path(
        "staff/savings/cash-withdrawal-requests/<int:request_id>/reject/",
        action_roles("staff")(views.staff_reject_cash_withdrawal),
        name="staff_reject_cash_withdrawal",
    ),

    # Staff confirms physical cash was handed to the client.
    # This is the step that actually deducts the savings funds.
    path(
        "staff/savings/cash-withdrawal-requests/<int:request_id>/confirm-payout/",
        action_roles("staff")(views.staff_confirm_cash_withdrawal_payout),
        name="staff_confirm_cash_withdrawal_payout",
    ),

    # ==========================================
    # SAVINGS INTEREST POSTING
    # ==========================================

    path(
        "staff/savings/<int:account_id>/interest/",
        action_roles("staff")(views.staff_post_interest),
        name="staff_post_interest",
    ),

    # ==========================================
    # EARLY WITHDRAWAL REVIEW
    # ==========================================

    path(
        "staff/savings/withdrawal-requests/<int:request_id>/approve/",
        action_roles("staff")(views.staff_approve_early_withdrawal),
        name="staff_approve_early_withdrawal",
    ),

    path(
        "staff/savings/withdrawal-requests/<int:request_id>/reject/",
        action_roles("staff")(views.staff_reject_early_withdrawal),
        name="staff_reject_early_withdrawal",
    ),

    # ==========================================
    # MATURED SAVINGS TRANSFER REVIEW
    # ==========================================

    path(
        "staff/savings/transfer-requests/<int:request_id>/approve/",
        action_roles("staff")(views.staff_approve_savings_transfer),
        name="staff_approve_savings_transfer",
    ),

    path(
        "staff/savings/transfer-requests/<int:request_id>/reject/",
        action_roles("staff")(views.staff_reject_savings_transfer),
        name="staff_reject_savings_transfer",
    ),
]