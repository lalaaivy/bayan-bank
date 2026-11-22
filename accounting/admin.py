
from django.contrib import admin

from .models import BankAccount, LedgerEntry


# --------------------------------------------------
# REGULAR BANK ACCOUNTS
# --------------------------------------------------

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        "account_number",
        "client",
        "balance",
        "status",
        "opened_at",
    )

    list_filter = (
        "status",
        "opened_at",
    )

    search_fields = (
        "account_number",
        "client__user__username",
    )

    readonly_fields = (
        "balance",
        "opened_at",
    )

    ordering = ("-opened_at",)

    def has_delete_permission(self, request, obj=None):
        return False


# --------------------------------------------------
# LEDGER ENTRIES (READ-ONLY)
# --------------------------------------------------

@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "entry_type",
        "amount",
        "savings_account",
        "loan",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
