
from django.urls import path

from accounts.sod import action_roles

from . import exports, views


urlpatterns = [

    # ==========================================
    # CLIENT PORTAL
    # ==========================================

    path(
        "portal/loans/",
        views.portal_loans,
        name="portal_loans",
    ),

    path(
        "portal/loans/apply/",
        views.portal_apply,
        name="portal_apply",
    ),

    path(
        "portal/loans/<int:loan_id>/agreement/",
        views.portal_loan_agreement,
        name="portal_loan_agreement",
    ),

    path(
        "portal/loans/<int:loan_id>/agreement/accept/",
        views.portal_accept_agreement,
        name="portal_accept_agreement",
    ),

    path(
        "portal/loans/<int:loan_id>/repay/",
        views.portal_loan_repay,
        name="portal_loan_repay",
    ),

    # ==========================================
    # LOAN OFFICER
    # ==========================================



    # ==========================================
    # STAFF LOAN MANAGEMENT
    # ==========================================

    path(
        "staff/loans/",
        views.staff_loans,
        name="staff_loans",
    ),

    path(
        "staff/loans/<int:loan_id>/",
        views.staff_loan,
        name="staff_loan",
    ),

    # ==========================================
    # LOAN APPROVAL
    # Loan Officer only
    # ==========================================

    path(
        "staff/loans/<int:loan_id>/approve/",
        action_roles("loan_officer")(
            views.staff_loan_approve
        ),
        name="staff_loan_approve",
    ),

    path(
        "staff/loans/<int:loan_id>/reject/",
        action_roles("loan_officer")(
            views.staff_loan_reject
        ),
        name="staff_loan_reject",
    ),

    # ==========================================
    # LOAN AGREEMENT CREATION
    # Loan Officer only
    # ==========================================

    path(
        "staff/loans/<int:loan_id>/agreement/create/",
        action_roles("loan_officer")(
            views.staff_create_agreement
        ),
        name="staff_create_agreement",
    ),

    # ==========================================
    # LOAN DISBURSEMENT
    # Staff only
    # ==========================================

    path(
        "staff/loans/<int:loan_id>/disburse/",
        action_roles("staff")(
            views.staff_loan_disburse
        ),
        name="staff_loan_disburse",
    ),

    # ==========================================
    # LOAN PAYMENT PROCESSING
    # Staff only
    # ==========================================

    path(
        "staff/loans/<int:loan_id>/pay/",
        action_roles("staff")(
            views.staff_loan_pay
        ),
        name="staff_loan_pay",
    ),

    # ==========================================
    # LOAN CALENDAR
    # ==========================================

    path(
        "calendar/",
        views.calendar_page,
        name="loan_calendar",
    ),

    path(
        "calendar/events/",
        views.calendar_events,
        name="loan_calendar_events",
    ),

    # ==========================================
    # DOCUMENTS AND AGREEMENTS
    # ==========================================

    path(
        "loans/<int:loan_id>/agreement/pdf/",
        views.loan_agreement_pdf,
        name="loan_agreement_pdf",
    ),

    path(
        "loans/<int:loan_id>/export/pdf/",
        exports.export_loan_pdf,
        name="export_loan_pdf",
    ),

    path(
        "loans/<int:loan_id>/export/excel/",
        exports.export_loan_excel,
        name="export_loan_excel",
    ),

    path(
        "loans/documents/<int:document_id>/download/",
        views.loan_document_download,
        name="loan_document_download",
    ),
]
