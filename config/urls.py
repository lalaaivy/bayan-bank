
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("savings.urls")),
    path("", include("loans.urls")),
    path("", include("accounting.urls")),
    path("chatbot/", include("chatbot.urls")),
]
