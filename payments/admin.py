from django.contrib import admin

from core.admin_mixins import RoleBasedAdminMixin

from .models import CashHandover, Payment, PromoCode


@admin.register(Payment)
class PaymentAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("order", "method", "status", "amount", "transaction_id", "created_at")
    list_filter = ("method", "status")
    search_fields = ("transaction_id", "order__order_uid")


@admin.register(CashHandover)
class CashHandoverAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("staff", "handover_date", "expected_amount", "submitted_amount", "variance", "status")
    list_filter = ("status", "handover_date")


@admin.register(PromoCode)
class PromoCodeAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "discount_amount", "discount_percent", "is_active", "valid_from", "valid_to", "used_count")
    list_filter = ("is_active",)
