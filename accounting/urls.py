from django.urls import path

from . import views
from . import bank_views
from . import client_views


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

    # Staff and admin banking transactions
    path(
        "staff/bank-transactions/",
        bank_views.bank_transactions,
        name="bank_transactions",
    ),
    path(
        "staff/bank-transactions/deposit/",
        bank_views.bank_deposit,
        name="bank_deposit",
    ),
    path(
        "staff/bank-transactions/withdraw/",
        bank_views.bank_withdraw,
        name="bank_withdraw",
    ),
    path(
        "staff/bank-transactions/transfer/",
        bank_views.bank_transfer,
        name="bank_transfer",
    ),

    # Admin bank account freeze/unfreeze
    path(
        "admin-panel/bank-accounts/<int:account_id>/toggle-status/",
        bank_views.admin_toggle_bank_account_status,
        name="admin_toggle_bank_account_status",
    ),

    # Client banking transactions
    path(
        "my-bank/",
        client_views.client_bank_page,
        name="client_bank_page",
    ),
    path(
        "my-bank/transfer/",
        client_views.client_bank_transfer_view,
        name="client_bank_transfer",
    ),
]