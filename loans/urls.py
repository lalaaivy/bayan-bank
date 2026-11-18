
from django.urls import path

from . import views, exports

urlpatterns = [
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
        "staff/loans/",
        views.staff_loans,
        name="staff_loans",
    ),
    path(
        "staff/loans/<int:loan_id>/",
        views.staff_loan,
        name="staff_loan",
    ),
    path(
        "staff/loans/<int:loan_id>/approve/",
        views.staff_loan_approve,
        name="staff_loan_approve",
    ),
    path(
        "staff/loans/<int:loan_id>/reject/",
        views.staff_loan_reject,
        name="staff_loan_reject",
    ),
    path(
        "staff/loans/<int:loan_id>/disburse/",
        views.staff_loan_disburse,
        name="staff_loan_disburse",
    ),
    path(
        "staff/loans/<int:loan_id>/pay/",
        views.staff_loan_pay,
        name="staff_loan_pay",
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
]
