from django.contrib import admin, messages

from core.admin_mixins import RoleBasedAdminMixin

from .models import DeliveryException, Order, OrderItem, RefillReminder, Subscription
from .services import cancel_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = (
        "order_uid", "customer", "order_type", "status", "payment_method",
        "total_amount", "assigned_staff", "created_at",
    )
    list_filter = ("status", "order_type", "payment_method", "is_express")
    search_fields = ("order_uid", "customer__username", "customer__phone")
    inlines = [OrderItemInline]
    actions = ["cancel_selected_orders"]

    # These fields are the *result* of app-level actions (cancel_order(),
    # and the delivery-app bottle exchange views) that also update related
    # models -- stock, promo used_count, CustomerBottleHolding,
    # BottleInventory. Hand-editing them here would change the number on
    # this one row without touching those related rows, silently
    # desyncing the data. Kept visible (read-only) rather than hidden, so
    # staff can still see the current state on this page -- status is
    # changed via the "Cancel selected orders" action below (the only
    # admin-safe transition off CREATED/CONFIRMED); the others change via
    # the delivery staff panel, which is where the matching inventory
    # updates happen.
    readonly_fields = ("status", "bottles_delivered", "empties_collected_good", "empties_collected_damaged")

    @admin.action(description="Cancel selected orders (stock/promo ফেরত দিয়ে)")
    def cancel_selected_orders(self, request, queryset):
        cancelled, skipped = 0, 0
        for order in queryset:
            ok, _message = cancel_order(order, cancelled_by=request.user)
            if ok:
                cancelled += 1
            else:
                skipped += 1
        if cancelled:
            self.message_user(
                request, f"{cancelled}টি অর্ডার বাতিল হয়েছে -- stock ও promo ব্যবহার ফেরত দেওয়া হয়েছে।",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped}টি অর্ডার বাতিল করা যায়নি (বর্তমান status থেকে বাতিল করার অনুমতি নেই -- "
                "ইতিমধ্যে assign/deliver/cancel হয়ে গেছে)।",
                level=messages.WARNING,
            )


@admin.register(DeliveryException)
class DeliveryExceptionAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("order", "reason", "reported_by", "is_resolved", "created_at")
    list_filter = ("reason", "is_resolved")


@admin.register(Subscription)
class SubscriptionAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("customer", "product", "interval", "is_active", "next_run_date")
    list_filter = ("interval", "is_active")


@admin.register(RefillReminder)
class RefillReminderAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("customer", "scheduled_for", "is_sent")
    list_filter = ("is_sent",)
