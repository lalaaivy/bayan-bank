from django.urls import path

from . import views

urlpatterns = [
    path("portal/savings/", views.portal_savings, name="portal_savings"),
    path("portal/savings/transfer/", views.portal_transfer, name="portal_transfer"),
    path("staff/savings/<int:account_id>/", views.staff_account, name="staff_account"),
    path("staff/savings/<int:account_id>/deposit/", views.staff_deposit, name="staff_deposit"),
    path("staff/savings/<int:account_id>/withdraw/", views.staff_withdraw, name="staff_withdraw"),
]