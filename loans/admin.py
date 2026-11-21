
from django.contrib import admin

from .models import (
    Disbursement,
    EligibilityCheck,
    Installment,
    Loan,
    LoanAgreement,
    LoanDocument,
    LoanPayment,
    LoanProduct,
    LoanRule,
)


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    can_delete = False
    fields = (
        "number",
        "due_date",
        "principal_due",
        "interest_due",
        "penalty_amount",
        "amount_paid",
        "status",
        "paid_at",
    )
    readonly_fields = fields


class LoanDocumentInline(admin.TabularInline):
    model = LoanDocument
    extra = 0
    can_delete = False
    fields = (
        "document_type",
        "file",
        "uploaded_at",
        "uploaded_by",
    )
    readonly_fields = fields


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "annual_rate",
        "min_amount",
        "max_amount",
        "min_months",
        "max_months",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "product",
        "principal",
        "annual_rate",
        "term_months",
        "status",
        "applied_at",
    )
    list_filter = (
        "status",
        "product",
        "applied_at",
    )
    search_fields = (
        "client__user__username",
        "client__user__first_name",
        "client__user__last_name",
        "product__name",
        "purpose",
    )
    readonly_fields = (
        "applied_at",
        "decided_at",
        "disbursed_at",
        "start_date",
    )
    ordering = ("-applied_at",)
    inlines = (
        InstallmentInline,
        LoanDocumentInline,
    )


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "number",
        "due_date",
        "principal_due",
        "interest_due",
        "penalty_amount",
        "amount_paid",
        "status",
    )
    list_filter = ("status", "due_date")
    search_fields = (
        "loan__client__user__username",
        "loan__product__name",
    )
    readonly_fields = (
        "loan",
        "number",
        "due_date",
        "principal_due",
        "interest_due",
        "penalty_amount",
        "amount_paid",
        "status",
        "paid_at",
    )
    ordering = ("due_date", "loan", "number")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "document_type",
        "uploaded_at",
        "uploaded_by",
    )
    list_filter = ("document_type", "uploaded_at")
    search_fields = (
        "loan__client__user__username",
        "loan__product__name",
    )
    readonly_fields = (
        "loan",
        "document_type",
        "file",
        "uploaded_at",
        "uploaded_by",
    )
    ordering = ("-uploaded_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoanRule)
class LoanRuleAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "minimum_monthly_income",
        "minimum_credit_score",
        "minimum_age",
        "max_installment_ratio",
        "min_savings_ratio",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("product__name",)


@admin.register(EligibilityCheck)
class EligibilityCheckAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "result",
        "checked_by",
        "checked_at",
    )
    list_filter = ("result", "checked_at")
    search_fields = (
        "loan__client__user__username",
        "loan__product__name",
        "remarks",
    )
    readonly_fields = (
        "loan",
        "result",
        "checked_by",
        "checked_at",
        "remarks",
    )
    ordering = ("-checked_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoanAgreement)
class LoanAgreementAdmin(admin.ModelAdmin):
    list_display = (
        "agreement_number",
        "loan",
        "agreement_date",
        "signed_at",
        "created_at",
    )
    search_fields = (
        "agreement_number",
        "loan__client__user__username",
    )
    list_filter = ("agreement_date", "signed_at")
    readonly_fields = (
        "agreement_number",
        "loan",
        "agreement_date",
        "signed_at",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "amount",
        "payment_date",
        "recorded_by",
    )
    list_filter = ("payment_date",)
    search_fields = (
        "loan__client__user__username",
        "ledger_entry__reference",
    )
    readonly_fields = (
        "loan",
        "amount",
        "payment_date",
        "recorded_by",
        "ledger_entry",
    )
    ordering = ("-payment_date",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan",
        "amount",
        "bank_account",
        "savings_account",
        "disbursed_at",
        "disbursed_by",
    )
    list_filter = ("disbursed_at",)
    search_fields = (
        "loan__client__user__username",
        "loan__product__name",
    )
    readonly_fields = (
        "loan",
        "amount",
        "bank_account",
        "savings_account",
        "disbursed_at",
        "disbursed_by",
    )
    ordering = ("-disbursed_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
