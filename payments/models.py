import uuid

from django.conf import settings
from django.db import models

from orders.models import Order


class Payment(models.Model):
    """Payment record for an order.

    Gateway integration (bKash / Nagad) is stubbed out in
    payments/gateways.py -- swap in real API credentials later without
    touching this model.
    """

    class Method(models.TextChoices):
        BKASH = "BKASH", "bKash"
        NAGAD = "NAGAD", "Nagad"
        COD = "COD", "Cash on Delivery"
        CORPORATE_POSTPAID = "CORPORATE_POSTPAID", "Corporate Postpaid (Invoiced)"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        INITIATED = "INITIATED", "Initiated"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        COD_PENDING = "COD_PENDING", "COD Pending"
        COD_COLLECTED = "COD_COLLECTED", "COD Collected"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100, blank=True)  # placeholder ref from gateway/dummy
    gateway_response = models.JSONField(blank=True, null=True)  # raw response, for debugging
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for {self.order} - {self.method} [{self.status}]"


class CashHandover(models.Model):
    """End-of-day COD cash reconciliation between a staff member and the hub/accounts."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Handover"
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified & Matched"
        MISMATCH = "MISMATCH", "Mismatch"

    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_handovers")
    handover_date = models.DateField()
    orders = models.ManyToManyField(Order, blank=True, related_name="cash_handovers")
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    submitted_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_handovers"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("staff", "handover_date")

    def __str__(self):
        return f"Cash Handover - {self.staff} - {self.handover_date}"

    @property
    def variance(self):
        return self.submitted_amount - self.expected_amount


class PromoCode(models.Model):
    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=255, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.code

    def is_valid_now(self):
        from django.utils import timezone

        now = timezone.now()
        if not self.is_active or now < self.valid_from or now > self.valid_to:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True
