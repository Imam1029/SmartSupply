from django.contrib import admin

from core.admin_mixins import RoleBasedAdminMixin

from .models import AuditLog, Notification, SMSLog


@admin.register(SMSLog)
class SMSLogAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("phone", "purpose", "status", "provider_message_id", "created_at")
    list_filter = ("status", "purpose")
    search_fields = ("phone", "message")


@admin.register(Notification)
class NotificationAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "kind", "title", "is_read", "created_at")
    list_filter = ("kind", "is_read")


@admin.register(AuditLog)
class AuditLogAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("actor", "action", "model_name", "object_id", "created_at")
    list_filter = ("action", "model_name")
