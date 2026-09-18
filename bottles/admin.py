from django.contrib import admin, messages
from django.db.models import Sum

from core.admin_mixins import RoleBasedAdminMixin
from core.utils import log_action

from .models import BottleInventory, CustomerBottleHolding, InventoryWriteOff


@admin.register(BottleInventory)
class BottleInventoryAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("product", "available_count", "damaged_count", "with_customers_count", "updated_at")
    readonly_fields = ("updated_at",)

    @admin.display(description="With customers")
    def with_customers_count(self, obj):
        return CustomerBottleHolding.objects.filter(product=obj.product).aggregate(total=Sum("quantity"))["total"] or 0


@admin.register(CustomerBottleHolding)
class CustomerBottleHoldingAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("customer", "product", "quantity", "updated_at")
    list_filter = ("product",)
    search_fields = ("customer__username", "customer__phone")


@admin.register(InventoryWriteOff)
class InventoryWriteOffAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    """
    Doubles as the "internal shrinkage / damage write-off" action -- a leak
    or broken bottle caught during washing/sanitization gets logged here
    directly (reason=SANITIZATION_DAMAGE, no related_order) by whoever runs
    the wash station. `save_model` applies the aggregate inventory effect
    automatically so this form is the only step needed for a *manually*
    created write-off; the field-collection path (delivery/views.py)
    creates these rows itself and has already applied its own inventory
    effect there, so we only apply it here for a write-off created
    *through this admin form* (guarded by `not change`, so editing an
    existing row later never re-applies the effect a second time).
    """

    list_display = ("product", "quantity", "reason", "performed_by", "related_order", "created_at")
    list_filter = ("reason", "product")
    readonly_fields = ("created_at",)

    def save_model(self, request, obj, form, change):
        if not change:
            if not obj.performed_by_id:
                obj.performed_by = request.user
            inventory, _ = BottleInventory.objects.get_or_create(product=obj.product)
            inventory.available_count = max(0, inventory.available_count - obj.quantity)
            inventory.damaged_count += obj.quantity
            inventory.save()
            log_action(request.user, "INTERNAL_SHRINKAGE_WRITEOFF", "BottleInventory", obj.product_id, quantity=obj.quantity, reason=obj.reason)
        super().save_model(request, obj, form, change)
        if not change:
            self.message_user(request, f"{obj.quantity}টি বোতল write-off করা হয়েছে, inventory আপডেট হয়েছে।", level=messages.SUCCESS)
