from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        ORDER_CONFIRMED = "ORDER_CONFIRMED", "Order Confirmed"
        PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED", "Payment Confirmed"
        ORDER_SHIPPED = "ORDER_SHIPPED", "Order Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        REFILL_REMINDER = "REFILL_REMINDER", "Refill Reminder"
        PAYMENT_REMINDER = "PAYMENT_REMINDER", "Payment Reminder"
        EXCEPTION_ALERT = "EXCEPTION_ALERT", "Exception Alert"
        STAFF_ASSIGNMENT = "STAFF_ASSIGNMENT", "Staff Assignment"
        ADMIN_ALERT = "ADMIN_ALERT", "Admin Alert"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.kind}] {self.title} -> {self.user}"


class SMSLog(models.Model):
    """Record of every SMS sent through the (currently demo) SMS gateway --
    mirrors what a real provider's dashboard would show you."""

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"

    phone = models.CharField(max_length=20)
    message = models.TextField()
    purpose = models.CharField(max_length=30, default="GENERAL")
    provider_message_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SMS to {self.phone} [{self.status}]"


class AuditLog(models.Model):
    """Generic activity/audit trail for sensitive admin & staff actions."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=50, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor} - {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
