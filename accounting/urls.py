
from django.urls import path

from . import views
from . import bank_views
from . import client_views


urlpatterns = [
    # Savings transaction exports
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

    # Staff bank transactions
    path(
        "bank/transactions/",
        bank_views.bank_transactions,
        name="bank_transactions",
    ),
    path(
        "bank/deposit/",
        bank_views.bank_deposit,
        name="bank_deposit",
    ),
    path(
        "bank/withdraw/",
        bank_views.bank_withdraw,
        name="bank_withdraw",
    ),
    path(
        "bank/transfer/",
        bank_views.bank_transfer,
        name="bank_transfer",
    ),

    # Client bank transactions
    path(
        "portal/bank/",
        client_views.client_bank_page,
        name="client_bank_page",
    ),
    path(
        "portal/bank/transfer/",
        client_views.client_bank_transfer_view,
        name="client_bank_transfer",
    ),
]
