from django.contrib import admin

from core.admin_mixins import RoleBasedAdminMixin

from .models import DeliveryIncentive, GPSPing, OfflineSyncEvent, Vehicle


@admin.register(Vehicle)
class VehicleAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("registration_number", "vehicle_type", "assigned_staff", "is_active")
    list_filter = ("vehicle_type", "is_active")


@admin.register(GPSPing)
class GPSPingAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("staff", "latitude", "longitude", "recorded_at")
    list_filter = ("staff",)


@admin.register(OfflineSyncEvent)
class OfflineSyncEventAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("staff", "event_type", "related_order", "sync_status", "occurred_at", "synced_at")
    list_filter = ("event_type", "sync_status")


@admin.register(DeliveryIncentive)
class DeliveryIncentiveAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("staff", "order", "amount", "is_paid", "created_at")
    list_filter = ("is_paid",)
