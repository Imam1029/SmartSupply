import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from accounts.models import Address
from orders.models import Order


class CorporateClient(models.Model):
    """An office / bank / school etc. that orders in bulk and settles
    monthly instead of paying per delivery (Phase 3 / B2B)."""

    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Monthly"
        BIWEEKLY = "BIWEEKLY", "Bi-weekly"

    company_name = models.CharField(max_length=200)
    contact_person = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="corporate_clients"
    )
    billing_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="corporate_clients")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing_cycle = models.CharField(max_length=10, choices=BillingCycle.choices, default=BillingCycle.MONTHLY)
    payment_terms_days = models.PositiveIntegerField(default=15, help_text="Due N days after invoice date")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name

    @property
    def current_outstanding(self):
        return sum(
            (inv.total_amount for inv in self.invoices.exclude(status=Invoice.Status.PAID)), Decimal("0")
        )

    @property
    def available_credit(self):
        return self.credit_limit - self.current_outstanding

    def can_place_order(self, amount):
        return self.is_active and amount <= self.available_credit


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"

    invoice_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    client = models.ForeignKey(CorporateClient, on_delete=models.CASCADE, related_name="invoices")
    period_start = models.DateField()
    period_end = models.DateField()
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    orders = models.ManyToManyField(Order, blank=True, related_name="corporate_invoices")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date"]

    def __str__(self):
        return f"Invoice {self.invoice_uid} - {self.client}"

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    def recalculate_total(self):
        self.total_amount = sum((o.total_amount for o in self.orders.all()), Decimal("0"))
        return self.total_amount
