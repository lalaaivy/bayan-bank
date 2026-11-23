from django.contrib import admin
from django.urls import include, path

from config import pwa


handler403 = "accounts.views.permission_denied"


urlpatterns = [
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

    # Main applications
    path("", include("accounts.urls")),
    path("", include("clients.urls")),
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