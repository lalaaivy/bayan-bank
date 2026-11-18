
from django.urls import path
from . import views

urlpatterns = [
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
]
