from django.contrib import admin

from core.admin_mixins import RoleBasedAdminMixin

from .models import Product


@admin.register(Product)
class ProductAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "bottle_size_liters", "water_price", "bottle_price", "available_stock", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
