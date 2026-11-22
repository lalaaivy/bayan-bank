
from django.contrib import admin

from .models import SavingsAccount, SavingsInterestPosting


@admin.register(SavingsAccount)
class SavingsAccountAdmin(admin.ModelAdmin):
    list_display = (
        "account_number",
        "client",
        "balance",
        "status",
        "opened_at",
    )
    search_fields = (
        "account_number",
        "client__user__username",
    )
    list_filter = ("status",)


@admin.register(SavingsInterestPosting)
class SavingsInterestPostingAdmin(admin.ModelAdmin):
    list_display = (
        "savings_account",
        "year",
        "month",
        "annual_rate",
        "amount",
        "posted_by",
        "posted_at",
    )
    search_fields = (
        "savings_account__account_number",
        "posted_by__username",
    )
    list_filter = ("year", "month")
    readonly_fields = (
        "savings_account",
        "ledger_entry",
        "year",
        "month",
        "annual_rate",
        "amount",
        "posted_by",
        "posted_at",
    )
