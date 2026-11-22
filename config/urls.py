
from django.contrib import admin
from django.urls import include, path

handler403 = "accounts.views.permission_denied"

urlpatterns = [
    path("admin/", admin.site.urls),

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
