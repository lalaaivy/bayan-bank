from django.contrib import admin
from django.urls import include, path

from config import pwa


handler403 = "accounts.views.permission_denied"


urlpatterns = [
    # Main application routes first.
    # Ensures /staff/ opens the staff dashboard.
    path("", include("accounts.urls")),

    # Client routes.
    # Keep before Django Admin for custom admin-related URLs.
    path("", include("clients.urls")),

    # Django Administration
    path("admin/", admin.site.urls),

    # PWA
    path(
        "service-worker.js",
        pwa.service_worker,
        name="service_worker",
    ),
    path(
        "offline/",
        pwa.offline_page,
        name="offline",
    ),

    # Other applications
    path("", include("savings.urls")),
    path("", include("loans.urls")),
    path("", include("accounting.urls")),

    # Notifications
    path(
        "notifications/",
        include("notifications.urls"),
    ),

    # AI Chatbot
    path(
        "chatbot/",
        include("chatbot.urls"),
    ),
]