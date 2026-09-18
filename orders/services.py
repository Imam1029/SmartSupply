from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from bottles.models import CustomerBottleHolding
from catalog.models import Product
from core.models import Notification
from core.utils import log_action
from payments.gateways import initiate_payment
from payments.models import Payment, PromoCode

from .models import Order, OrderItem


class InsufficientStockError(ValidationError):
    pass


CANCELLABLE_STATUSES = (Order.Status.CREATED, Order.Status.CONFIRMED)


def apply_promo_code(order, code):
    """Validate and apply a promo code to an already-created order.
    Returns (success: bool, message: str)."""
    if not code:
        return False, ""
    try:
        promo = PromoCode.objects.get(code__iexact=code.strip())
    except PromoCode.DoesNotExist:
        return False, "প্রোমো কোড খুঁজে পাওয়া যায়নি।"

    if not promo.is_valid_now():
        return False, "এই প্রোমো কোডের মেয়াদ শেষ হয়ে গেছে বা এটি নিষ্ক্রিয়।"

    # Claim one use of the code atomically BEFORE applying the discount.
    # A plain `used_count += 1; save()` is a read-modify-write: two
    # customers redeeming the last remaining use at the same moment would
    # both pass is_valid_now() and both get the discount. The conditional
    # UPDATE below lets the database settle it -- if it matches 0 rows,
    # someone else took the last use.
    claim = PromoCode.objects.filter(pk=promo.pk)
    if promo.max_uses is not None:
        claim = claim.filter(used_count__lt=promo.max_uses)
    if not claim.update(used_count=F("used_count") + 1):
        return False, "এই প্রোমো কোডের ব্যবহারের সীমা শেষ হয়ে গেছে।"

    subtotal = order.water_amount + order.bottle_amount + order.delivery_charge + order.express_fee
    discount = promo.discount_amount
    if promo.discount_percent:
        discount += subtotal * (promo.discount_percent / 100)
    discount = min(discount, subtotal)

    order.promo_code = promo
    order.discount_amount = discount
    order.recalculate_total()
    order.save()

    log_action(order.customer, "PROMO_CODE_APPLIED", "Order", order.pk, code=promo.code, discount=str(discount))
    return True, f"প্রোমো কোড '{promo.code}' প্রয়োগ হয়েছে, ৳{discount} ছাড় পেয়েছেন।"


def grant_referral_reward_if_first_order(customer):
    """Referral & Loyalty (Phase 2): the first time a referred customer
    completes an order, grant the referrer their reward points."""
    referral = getattr(customer, "referred_by", None)
    if referral is None or referral.is_reward_granted:
        return
    if customer.orders.count() != 1:
        return  # only fire on the customer's very first order

    from accounts.models import LoyaltyPoint

    points = 50  # flat reward for MVP; make configurable later
    referral.reward_points = points
    referral.is_reward_granted = True
    referral.save()

    LoyaltyPoint.objects.create(
        user=referral.referrer, points=points, reason=f"Referral reward: {customer} completed first order"
    )
    Notification.objects.create(
        user=referral.referrer,
        kind=Notification.Kind.ADMIN_ALERT,
        title="রেফারেল পয়েন্ট পেয়েছেন!",
        message=f"আপনার রেফার করা {customer.get_full_name() or customer.phone} প্রথম অর্ডার সম্পন্ন করেছে। "
                f"আপনি {points} পয়েন্ট পেয়েছেন।",
    )
    log_action(referral.referrer, "REFERRAL_REWARD_GRANTED", "Referral", referral.pk, points=points)


@transaction.atomic
def create_order(*, customer, address, items, payment_method, is_express=False, promo_code=None,
                  corporate_client=None):
    """Create an Order + OrderItem(s) + Payment record for a customer
    (logged-in or guest). Centralised here so order_create_view, the cart
    checkout flow, and the guest/admin-phone-order flows can't drift apart.

    `items` is a list of {"product": Product, "quantity": int} dicts --
    multi-item cart support means refill/first-purchase is now determined
    *per item* (see OrderItem.is_refill), not once for the whole order.
    Order.order_type is kept as a simple summary label (FIRST_PURCHASE if
    every item is, REFILL if every item is, MIXED otherwise) for order-list
    display -- delivery views should read OrderItem.is_refill, not this.

    Runs in a single transaction: an Order with no Payment row, or stock
    decremented for an order that was never created, would both be silent
    data corruption that only shows up days later in the accounts. If any
    item in the cart fails its stock check, the whole order rolls back --
    including stock already reserved for earlier items in the same cart --
    rather than placing a partial order.
    """
    if not items:
        raise ValidationError("অর্ডারে অন্তত একটা item থাকতে হবে।")

    line_data = []  # (product, quantity, is_refill, water_amount, bottle_amount)
    for entry in items:
        product, quantity = entry["product"], entry["quantity"]

        # Lock this customer's holding row (if any) for the duration of the
        # transaction -- otherwise two concurrent checkouts for the same
        # customer+product (e.g. a double-tapped submit button) could both
        # read the same held_qty and both be treated as a refill.
        holding = CustomerBottleHolding.objects.select_for_update().filter(
            customer=customer, product=product
        ).first()
        held_qty = holding.quantity if holding else 0
        is_refill = held_qty >= quantity

        # Reserve stock with one conditional UPDATE rather than
        # check-then-subtract. Under two simultaneous orders for the last
        # bottle, the old read-modify-write let both through and drove
        # available_stock negative; here the second UPDATE matches 0 rows
        # and is rejected cleanly.
        if not is_refill:
            reserved = Product.objects.filter(pk=product.pk, available_stock__gte=quantity).update(
                available_stock=F("available_stock") - quantity
            )
            if not reserved:
                product.refresh_from_db(fields=["available_stock"])
                raise InsufficientStockError(
                    f"'{product.name}'-এর জন্য যথেষ্ট স্টক নেই। বর্তমান স্টক: {product.available_stock}"
                )

        water_amount = product.water_price * quantity
        bottle_amount = 0 if is_refill else product.bottle_price * quantity
        line_data.append((product, quantity, is_refill, water_amount, bottle_amount))

    refill_flags = {is_refill for *_, is_refill, _, _ in line_data}
    if refill_flags == {True}:
        order_type = Order.OrderType.REFILL
    elif refill_flags == {False}:
        order_type = Order.OrderType.FIRST_PURCHASE
    else:
        order_type = Order.OrderType.MIXED

    water_amount = sum(w for *_, w, _b in line_data)
    bottle_amount = sum(b for *_, _w, b in line_data)
    express_fee = settings.EXPRESS_DELIVERY_FEE if is_express else 0
    delivery_charge = settings.STANDARD_DELIVERY_CHARGE

    order = Order.objects.create(
        customer=customer,
        delivery_address=address,
        order_type=order_type,
        payment_method=payment_method,
        is_express=is_express,
        express_fee=express_fee,
        delivery_charge=delivery_charge,
        water_amount=water_amount,
        bottle_amount=bottle_amount,
        corporate_client=corporate_client,
    )
    for product, quantity, is_refill, _water, _bottle in line_data:
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit_water_price=product.water_price,
            unit_bottle_price=0 if is_refill else product.bottle_price,
            is_refill=is_refill,
        )
        # (stock for non-refill items was already reserved above, in the
        # same transaction, via the conditional UPDATE -- not repeated here)

    order.recalculate_total()
    order.save()

    promo_message = ""
    if promo_code:
        _, promo_message = apply_promo_code(order, promo_code)

    if payment_method == Order.PaymentMethod.CORPORATE_POSTPAID:
        Payment.objects.create(
            order=order, method=Payment.Method.CORPORATE_POSTPAID, status=Payment.Status.PENDING,
            amount=order.total_amount,
        )
    elif payment_method in (Order.PaymentMethod.BKASH, Order.PaymentMethod.NAGAD):
        result = initiate_payment(payment_method, order.total_amount, order.order_uid)
        Payment.objects.create(
            order=order,
            method=payment_method,
            status=Payment.Status.INITIATED,
            amount=order.total_amount,
            transaction_id=result.transaction_id,
            gateway_response=result.raw_response,
        )
    else:
        Payment.objects.create(
            order=order, method=Payment.Method.COD, status=Payment.Status.COD_PENDING, amount=order.total_amount
        )

    Notification.objects.create(
        user=customer,
        kind=Notification.Kind.ORDER_CONFIRMED,
        title="অর্ডার তৈরি হয়েছে",
        message=f"আপনার অর্ডার {order.order_uid} সফলভাবে তৈরি হয়েছে।",
    )

    log_action(customer, "ORDER_CREATED", "Order", order.pk, order_type=order_type, total=str(order.total_amount))

    grant_referral_reward_if_first_order(customer)

    order._promo_message = promo_message  # transient, read by the view for a flash message
    return order


def has_conflicting_active_subscription(customer, product):
    """Used to warn a customer placing a manual order while an auto-refill
    subscription for the same product is already active (Phase 2 duplicate-
    order alert)."""
    return customer.subscriptions.filter(product=product, is_active=True).exists()


@transaction.atomic
def cancel_order(order, cancelled_by):
    """Cancel an order that hasn't been assigned/shipped yet. Restores stock
    consumed by any first-purchase item(s), releases any promo-code use it
    claimed, and marks the payment cancelled."""
    # Lock this order row for the duration: without it, two taps on the
    # Cancel button (or a tap plus an admin cancelling at the same moment)
    # both read status=CREATED and both restore the stock, inventing
    # bottles that don't exist.
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status not in CANCELLABLE_STATUSES:
        return False, "এই অর্ডারটি এখন আর বাতিল করা যাবে না (ইতিমধ্যে প্রসেস শুরু হয়ে গেছে)।"

    for item in order.items.filter(is_refill=False):
        Product.objects.filter(pk=item.product_id).update(
            available_stock=F("available_stock") + item.quantity
        )

    # Give the promo-code use back, otherwise a limited-use campaign burns
    # through max_uses on orders that were never delivered.
    if order.promo_code_id:
        PromoCode.objects.filter(pk=order.promo_code_id, used_count__gt=0).update(
            used_count=F("used_count") - 1
        )

    order.status = Order.Status.CANCELLED
    order.save()

    payment = getattr(order, "payment", None)
    if payment and payment.status not in (Payment.Status.SUCCESS, Payment.Status.COD_COLLECTED):
        payment.status = Payment.Status.FAILED
        payment.save()

    Notification.objects.create(
        user=order.customer,
        kind=Notification.Kind.ADMIN_ALERT,
        title="অর্ডার বাতিল হয়েছে",
        message=f"আপনার অর্ডার {order.order_uid} বাতিল করা হয়েছে।",
    )
    log_action(cancelled_by, "ORDER_CANCELLED", "Order", order.pk)
    return True, "অর্ডার সফলভাবে বাতিল হয়েছে।"
