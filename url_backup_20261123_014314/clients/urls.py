
from django.urls import path

from . import views

urlpatterns = [
    path(
        "staff/clients/",
        views.staff_clients,
        name="staff_clients",
    ),
    path(
        "staff/clients/<int:client_id>/",
        views.staff_client_detail,
        name="staff_client_detail",
    ),
]
