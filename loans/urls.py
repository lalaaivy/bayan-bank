from django.urls import path
from . import views

urlpatterns = [
    path("portal/loans/", views.my_loans, name="my_loans"),
]