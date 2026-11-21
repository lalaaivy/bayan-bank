
from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "kind",
        "message",
        "is_read",
        "created_at",
    )

    list_filter = (
        "kind",
        "is_read",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "message",
    )

    readonly_fields = (
        "user",
        "kind",
        "message",
        "is_read",
        "created_at",
    )

    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
