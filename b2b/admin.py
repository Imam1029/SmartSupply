from django.contrib import admin, messages

from core.admin_mixins import RoleBasedAdminMixin

from .models import CorporateClient, Invoice
from .services import generate_invoice_for_client


@admin.register(CorporateClient)
class CorporateClientAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = (
        "company_name", "contact_person", "credit_limit", "current_outstanding",
        "available_credit", "billing_cycle", "is_active",
    )
    list_filter = ("billing_cycle", "is_active")
    search_fields = ("company_name", "contact_person__phone", "contact_person__username")
    actions = ["generate_invoice_now"]

    @admin.action(description="Generate invoice for all un-invoiced orders (last 30 days)")
    def generate_invoice_now(self, request, queryset):
        created = 0
        for client in queryset:
            invoice = generate_invoice_for_client(client)
            if invoice:
                created += 1
        if created:
            self.message_user(request, f"{created}টি নতুন invoice তৈরি হয়েছে।", level=messages.SUCCESS)
        else:
            self.message_user(request, "কোনো un-invoiced অর্ডার পাওয়া যায়নি।", level=messages.INFO)


@admin.register(Invoice)
class InvoiceAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("invoice_uid", "client", "period_start", "period_end", "due_date", "total_amount", "amount_paid", "status")
    list_filter = ("status", "client")
    readonly_fields = ("invoice_uid", "issue_date")
