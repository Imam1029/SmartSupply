import uuid

from django.conf import settings
from django.db import models

from accounts.models import Address
from catalog.models import Product


class Order(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Order Created"
        CONFIRMED = "CONFIRMED", "Admin Confirmed"
        ASSIGNED = "ASSIGNED", "Staff Assigned"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for Delivery"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed / Exception"
        CANCELLED = "CANCELLED", "Cancelled"

    class OrderType(models.TextChoices):
        FIRST_PURCHASE = "FIRST_PURCHASE", "First Purchase"
        REFILL = "REFILL", "Refill"
        MIXED = "MIXED", "Mixed (Multi-item)"

    class PaymentMethod(models.TextChoices):
        BKASH = "BKASH", "bKash"
        NAGAD = "NAGAD", "Nagad"
        COD = "COD", "Cash on Delivery"
        CORPORATE_POSTPAID = "CORPORATE_POSTPAID", "Corporate Postpaid (Invoiced)"

    order_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    delivery_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="orders")

    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    is_express = models.BooleanField(default=False)
    express_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    water_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bottle_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promo_code = models.ForeignKey(
        "payments.PromoCode", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_orders"
    )
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="phone_orders_placed",
        help_text="Admin/staff যদি ফোন কলে কাস্টমারের হয়ে অর্ডার বসিয়ে থাকে, সেই staff -- self-service/guest অর্ডারে null থাকে।",
    )
    corporate_client = models.ForeignKey(
        "b2b.CorporateClient", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders_placed"
    )
    # Aggregate exchange counts -- no per-unit bottle reference (see
    # bottles.models for why). Filled in by the delivery-app views when
    # staff completes the full-bottle-for-empty exchange.
    bottles_delivered = models.PositiveIntegerField(default=0)
    empties_collected_good = models.PositiveIntegerField(default=0)
    empties_collected_damaged = models.PositiveIntegerField(default=0)

    is_subscription_order = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_uid} - {self.customer}"

    def recalculate_total(self):
        subtotal = self.water_amount + self.bottle_amount + self.delivery_charge + self.express_fee
        self.total_amount = max(subtotal - self.discount_amount, 0)
        return self.total_amount


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_water_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_bottle_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_refill = models.BooleanField(
        default=False,
        help_text="Per-item refill vs first-purchase (multi-item cart means one order can mix both) -- "
                   "set at order creation, read by delivery views instead of the old whole-order Order.order_type.",
    )

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def line_total(self):
        return self.quantity * (self.unit_water_price + self.unit_bottle_price)


class DeliveryException(models.Model):
    class Reason(models.TextChoices):
        CUSTOMER_UNAVAILABLE = "CUSTOMER_UNAVAILABLE", "Customer Unavailable"
        WRONG_ADDRESS = "WRONG_ADDRESS", "Wrong Address"
        CUSTOMER_REFUSED = "CUSTOMER_REFUSED", "Customer Refused Delivery"
        PAYMENT_ISSUE = "PAYMENT_ISSUE", "Payment Issue"
        BOTTLE_ISSUE = "BOTTLE_ISSUE", "Bottle Issue"
        OTHER = "OTHER", "Other"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="exceptions")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=30, choices=Reason.choices)
    note = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Exception on {self.order} - {self.reason}"


class Subscription(models.Model):
    class Interval(models.TextChoices):
        WEEKLY = "WEEKLY", "Weekly"
        BIWEEKLY = "BIWEEKLY", "Bi-weekly"
        MONTHLY = "MONTHLY", "Monthly"
        CUSTOM = "CUSTOM", "Custom"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    address = models.ForeignKey(Address, on_delete=models.PROTECT)
    interval = models.CharField(max_length=10, choices=Interval.choices, default=Interval.WEEKLY)
    custom_days = models.PositiveIntegerField(null=True, blank=True, help_text="Used when interval=CUSTOM")
    is_active = models.BooleanField(default=True)
    next_run_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Subscription: {self.customer} - {self.product} ({self.interval})"

    @property
    def interval_days(self):
        return {
            self.Interval.WEEKLY: 7,
            self.Interval.BIWEEKLY: 14,
            self.Interval.MONTHLY: 30,
        }.get(self.interval, self.custom_days or 7)

    def advance_next_run_date(self):
        """Push next_run_date forward by one interval -- used both for the
        customer-facing 'skip next delivery' action and (later) by the
        scheduler after an auto-refill order is actually placed."""
        from datetime import timedelta

        from django.utils import timezone

        base = self.next_run_date or timezone.localdate()
        self.next_run_date = base + timedelta(days=self.interval_days)
        self.save(update_fields=["next_run_date"])
        return self.next_run_date


class RefillReminder(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refill_reminders")
    message = models.CharField(max_length=255, default="Your next refill may be due.")
    is_sent = models.BooleanField(default=False)
    scheduled_for = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reminder for {self.customer} @ {self.scheduled_for}"
