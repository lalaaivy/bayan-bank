
from django.urls import path
from . import views

urlpatterns = [
    # Savings account statements
    path(
        "accounts/<int:account_id>/transactions/pdf/",
        views.export_transactions_pdf,
        name="export_transactions_pdf",
    ),
    path(
        "accounts/<int:account_id>/transactions/excel/",
        views.export_transactions_excel,
        name="export_transactions_excel",
    ),

    # Regular bank account statements
    path(
        "bank-accounts/<int:account_id>/transactions/pdf/",
        views.export_bank_transactions_pdf,
        name="export_bank_transactions_pdf",
    ),
    path(
        "bank-accounts/<int:account_id>/transactions/excel/",
        views.export_bank_transactions_excel,
        name="export_bank_transactions_excel",
    ),
]
