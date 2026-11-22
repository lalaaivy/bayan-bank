
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .role_dashboard import role_dashboard


urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),
    path(
        "login/",
        auth_views.LoginView.as_view(),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "portal/",
        views.portal_home,
        name="portal_home",
    ),
    path(
        "staff/",
        role_dashboard,
        name="staff_home",
    ),
]
