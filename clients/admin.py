
from django.contrib import admin

from .models import Client, ClientDocument


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_code",
        "user",
        "phone",
        "verification_status",
        "credit_score",
        "created_at",
    )

    list_filter = (
        "verification_status",
        "sex",
        "civil_status",
        "employment_status",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "phone",
        "id_number_hash",
    )

    readonly_fields = (
        "id_number_encrypted",
        "id_number_hash",
        "created_at",
        "verified_at",
    )

    ordering = ("-created_at",)


@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "id_type",
        "status",
        "uploaded_at",
        "reviewed_by",
    )

    list_filter = (
        "id_type",
        "status",
        "uploaded_at",
    )

    search_fields = (
        "client__user__username",
        "client__user__first_name",
        "client__user__last_name",
    )

    readonly_fields = (
        "client",
        "id_type",
        "front_image",
        "back_image",
        "uploaded_at",
        "reviewed_by",
        "reviewed_at",
        "remark",
    )

    ordering = ("-uploaded_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
