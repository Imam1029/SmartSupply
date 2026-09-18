from datetime import timedelta

from django.utils import timezone

from core.utils import log_action
from orders.models import Order
from orders.services import create_order

from .models import Invoice


def place_corporate_order(*, client, address, product, quantity, placed_by):
    """Place a postpaid order for a corporate client, enforcing its credit
    limit before the order is created."""
    # Safe overestimate for the credit check: includes bottle price even
    # though a refill wouldn't actually charge it -- better to occasionally
    # block an order that would've fit than to let one through that
    # doesn't, and CustomerBottleHolding isn't checked here to keep this a
    # single cheap query rather than duplicating create_order()'s own logic.
    estimated = (product.water_price + product.bottle_price) * quantity
    if not client.can_place_order(estimated):
        return None, (
            f"Credit limit অতিক্রম করছে। Available credit: ৳{client.available_credit}, "
            f"এই অর্ডারের আনুমানিক মূল্য: ৳{estimated}"
        )

    order = create_order(
        customer=client.contact_person,
        address=address,
        items=[{"product": product, "quantity": quantity}],
        payment_method=Order.PaymentMethod.CORPORATE_POSTPAID,
        corporate_client=client,
    )
    log_action(placed_by, "CORPORATE_ORDER_PLACED", "Order", order.pk, client=client.company_name)
    return order, ""


def generate_invoice_for_client(client, period_days=30):
    """Bundle every not-yet-invoiced Corporate Postpaid order for this client
    into a new Invoice (Phase 3 demo of monthly billing)."""
    uninvoiced_orders = Order.objects.filter(
        corporate_client=client,
        payment_method=Order.PaymentMethod.CORPORATE_POSTPAID,
    ).exclude(corporate_invoices__isnull=False)

    if not uninvoiced_orders.exists():
        return None

    today = timezone.localdate()
    invoice = Invoice.objects.create(
        client=client,
        period_start=today - timedelta(days=period_days),
        period_end=today,
        due_date=today + timedelta(days=client.payment_terms_days),
        status=Invoice.Status.ISSUED,
    )
    invoice.orders.set(uninvoiced_orders)
    invoice.recalculate_total()
    invoice.save()
    log_action(client.contact_person, "INVOICE_GENERATED", "Invoice", invoice.pk, amount=str(invoice.total_amount))
    return invoice
