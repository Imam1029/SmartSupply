from django.conf import settings
from django.db import models

from orders.models import Order


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        BIKE = "BIKE", "Motorbike"
        VAN = "VAN", "Van"
        RICKSHAW_VAN = "RICKSHAW_VAN", "Rickshaw Van"
        TRUCK = "TRUCK", "Truck"

    registration_number = models.CharField(max_length=50, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="vehicles"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.registration_number} ({self.vehicle_type})"


class GPSPing(models.Model):
    """Periodic location ping from a staff member's mobile device (Phase 2 feature)."""

    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gps_pings")
    latitude = models.DecimalField(max_digits=10, decimal_places=6)
    longitude = models.DecimalField(max_digits=10, decimal_places=6)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.staff} @ ({self.latitude}, {self.longitude})"


class OfflineSyncEvent(models.Model):
    """An action a staff member performed while offline, queued for later sync.

    Server-authoritative model: when the device reconnects, each event is
    replayed against current server state. Conflicting events are flagged
    for manual resolution rather than blindly applied.
    """

    class EventType(models.TextChoices):
        DELIVERY_CONFIRM = "DELIVERY_CONFIRM", "Delivery Confirm"
        BOTTLE_COLLECT = "BOTTLE_COLLECT", "Bottle Collect"
        BOTTLE_CONDITION = "BOTTLE_CONDITION", "Bottle Condition Update"
        PAYMENT_COLLECT = "PAYMENT_COLLECT", "Payment Collect"
        EXCEPTION_REPORT = "EXCEPTION_REPORT", "Exception Report"

    class SyncStatus(models.TextChoices):
        QUEUED = "QUEUED", "Queued on Device"
        SYNCING = "SYNCING", "Syncing"
        ACCEPTED = "ACCEPTED", "Accepted"
        CONFLICT = "CONFLICT", "Conflict - Needs Review"
        REJECTED = "REJECTED", "Rejected"

    local_event_id = models.CharField(max_length=100, help_text="Client-generated UUID for idempotency")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offline_events")
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    related_order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    device_reference = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField(help_text="When the action actually happened on the device")
    synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=10, choices=SyncStatus.choices, default=SyncStatus.QUEUED)
    conflict_note = models.TextField(blank=True)

    class Meta:
        unique_together = ("staff", "local_event_id")
        ordering = ["occurred_at"]

    def __str__(self):
        return f"{self.event_type} by {self.staff} [{self.sync_status}]"


class DeliveryIncentive(models.Model):
    """Auto-calculated bonus per successful delivery / collected bottle (Phase 2)."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="incentive")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="incentives")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Incentive {self.amount} for {self.staff} - {self.order}"
