from django.conf import settings
from django.db import models

from catalog.models import Product


class BottleInventory(models.Model):
    """
    Aggregate bottle stock for one product -- no per-unit/serialized
    tracking. Per the final spec: individual bottles are NOT tracked
    per-unit (no QR/barcode, no per-bottle history) -- only simple exchange
    counts are kept. `available_count` is company-owned bottles sitting at
    the hub, sanitized and ready to hand out. `damaged_count` is a running
    cumulative total of bottles written off (damaged/unusable/lost) -- kept
    for reporting, never decremented. How many bottles are currently out
    with customers isn't stored here directly; it's the sum of
    `CustomerBottleHolding.quantity` for this product (see that model).
    """

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="inventory")
    available_count = models.PositiveIntegerField(default=0)
    damaged_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} -- {self.available_count} available"


class CustomerBottleHolding(models.Model):
    """How many company bottles a given customer currently holds, per
    product. This is the aggregate replacement for per-unit
    `current_holder` -- we only need the count to (a) auto-detect
    first-purchase vs refill on the next order and (b) know how many to
    expect back on collection."""

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bottle_holdings")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="customer_holdings")
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("customer", "product")

    def __str__(self):
        return f"{self.customer} holds {self.quantity}x {self.product.name}"


class InventoryWriteOff(models.Model):
    """
    Internal shrinkage / damage write-off -- a leak or broken bottle caught
    during washing/sanitization, or a damaged/unusable bottle collected in
    the field. Deducts from the company's owned bottle count; the running
    total lives on `BottleInventory.damaged_count`, this is the audit trail
    of *why*.
    """

    class Reason(models.TextChoices):
        SANITIZATION_DAMAGE = "SANITIZATION_DAMAGE", "Found Damaged During Sanitization"
        FIELD_COLLECTION_DAMAGED = "FIELD_COLLECTION_DAMAGED", "Damaged -- Collected From Customer"
        FIELD_COLLECTION_UNUSABLE = "FIELD_COLLECTION_UNUSABLE", "Unusable -- Collected From Customer"
        LOST = "LOST", "Reported Lost"
        OTHER = "OTHER", "Other"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="write_offs")
    quantity = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    note = models.TextField(blank=True)
    related_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="write_offs"
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="write_offs_logged"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Write-off: {self.quantity}x {self.product.name} ({self.reason})"
