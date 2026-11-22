from django.contrib import admin

from .models import BankAccount, LedgerEntry, ReportExport


# --------------------------------------------------
# REGULAR BANK ACCOUNTS (READ-ONLY)
# --------------------------------------------------

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
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
        "client__user__first_name",
        "client__user__last_name",
    )

    readonly_fields = (
        "client",
        "account_number",
        "balance",
        "status",
        "opened_at",
    )

    ordering = ("-opened_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

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
        "bank_account",
        "savings_account",
        "loan",
        "reference",
        "created_by",
        "created_at",
    )

    list_filter = (
        "entry_type",
        "created_at",
    )

    search_fields = (
        "reference",
        "bank_account__account_number",
        "savings_account__account_number",
        "created_by__username",
    )

    readonly_fields = (
        "entry_type",
        "amount",
        "balance_after",
        "bank_account",
        "savings_account",
        "loan",
        "reference",
        "created_by",
        "created_at",
    )

    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --------------------------------------------------
# REPORT EXPORTS (READ-ONLY)
# --------------------------------------------------

@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filename",
        "report_type",
        "file_format",
        "generated_by",
        "generated_at",
    )

    list_filter = (
        "report_type",
        "file_format",
        "generated_at",
    )

    search_fields = (
        "filename",
        "generated_by__username",
    )

    readonly_fields = (
        "report_type",
        "file_format",
        "bank_account",
        "savings_account",
        "loan",
        "date_from",
        "date_to",
        "generated_by",
        "generated_at",
        "filename",
    )

    date_hierarchy = "generated_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False