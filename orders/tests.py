"""Tests for the multi-item order lifecycle: pricing, stock accounting,
promo codes, cancellation rules, and the POST-only guard on destructive
actions.

These target `orders/services.py` (create_order / cancel_order /
apply_promo_code) rather than the views, since that's where the money and
inventory arithmetic actually lives -- the views (quick order, cart
checkout, guest checkout, admin phone order, reorder) are thin wrappers
around it and all funnel through the same functions.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, Role
from bottles.models import CustomerBottleHolding
from catalog.models import Product
from payments.models import Payment, PromoCode

from .models import Order
from .services import InsufficientStockError, apply_promo_code, cancel_order, create_order

User = get_user_model()


class OrderTestBase(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="01800000001", phone="01800000001", password="custpass123", role=Role.CUSTOMER
        )
        self.address = Address.objects.create(
            user=self.customer, label="Home", full_address="Test Road, Chattogram", is_default=True
        )
        self.jar = Product.objects.create(
            name="Test Jar", bottle_size_liters=Decimal("20"),
            water_price=Decimal("80"), bottle_price=Decimal("220"),
            available_stock=10,
        )
        self.small = Product.objects.create(
            name="Test Small Bottle", bottle_size_liters=Decimal("5"),
            water_price=Decimal("30"), bottle_price=Decimal("100"),
            available_stock=10,
        )

    def place(self, items=None, **kwargs):
        if items is None:
            items = [{"product": self.jar, "quantity": 1}]
        defaults = dict(
            customer=self.customer, address=self.address,
            payment_method=Order.PaymentMethod.COD,
        )
        defaults.update(kwargs)
        return create_order(items=items, **defaults)

    def stock(self, product=None):
        product = product or self.jar
        product.refresh_from_db()
        return product.available_stock


class PricingTests(OrderTestBase):
    def test_first_order_charges_water_plus_bottle(self):
        order = self.place(items=[{"product": self.jar, "quantity": 2}])
        self.assertEqual(order.order_type, Order.OrderType.FIRST_PURCHASE)
        self.assertEqual(order.water_amount, Decimal("160"))
        self.assertEqual(order.bottle_amount, Decimal("440"))
        self.assertEqual(order.total_amount, Decimal("600"))

    def test_refill_charges_water_only_when_customer_holds_a_bottle(self):
        CustomerBottleHolding.objects.create(customer=self.customer, product=self.jar, quantity=1)
        order = self.place()
        self.assertEqual(order.order_type, Order.OrderType.REFILL)
        self.assertEqual(order.bottle_amount, Decimal("0"))
        self.assertEqual(order.total_amount, Decimal("80"))

    def test_cod_order_creates_a_pending_cod_payment(self):
        order = self.place()
        self.assertEqual(order.payment.method, Payment.Method.COD)
        self.assertEqual(order.payment.amount, order.total_amount)


class CartMultiItemTests(OrderTestBase):
    def test_mixed_cart_prices_each_item_by_its_own_refill_status(self):
        # Customer already holds a jar (refill) but has never held the
        # small bottle (first purchase) -- one order, two different rules.
        CustomerBottleHolding.objects.create(customer=self.customer, product=self.jar, quantity=1)
        order = self.place(items=[
            {"product": self.jar, "quantity": 1},
            {"product": self.small, "quantity": 2},
        ])
        self.assertEqual(order.order_type, Order.OrderType.MIXED)
        self.assertEqual(order.water_amount, Decimal("80") + Decimal("60"))  # jar refill + 2x small water
        self.assertEqual(order.bottle_amount, Decimal("200"))  # only the 2 small bottles charged
        self.assertEqual(order.items.count(), 2)

    def test_all_first_purchase_items_gives_first_purchase_order_type(self):
        order = self.place(items=[
            {"product": self.jar, "quantity": 1}, {"product": self.small, "quantity": 1},
        ])
        self.assertEqual(order.order_type, Order.OrderType.FIRST_PURCHASE)

    def test_empty_cart_is_rejected(self):
        with self.assertRaises(Exception):
            self.place(items=[])


class StockTests(OrderTestBase):
    def test_first_purchase_consumes_stock(self):
        self.place(items=[{"product": self.jar, "quantity": 3}])
        self.assertEqual(self.stock(), 7)

    def test_refill_does_not_consume_stock(self):
        CustomerBottleHolding.objects.create(customer=self.customer, product=self.jar, quantity=3)
        self.place(items=[{"product": self.jar, "quantity": 3}])
        self.assertEqual(self.stock(), 10)

    def test_order_beyond_available_stock_is_rejected(self):
        with self.assertRaises(InsufficientStockError):
            self.place(items=[{"product": self.jar, "quantity": 11}])
        self.assertEqual(self.stock(), 10)

    def test_stock_never_goes_negative_when_reserving_the_last_units(self):
        self.place(items=[{"product": self.jar, "quantity": 10}])
        self.assertEqual(self.stock(), 0)
        with self.assertRaises(InsufficientStockError):
            self.place(items=[{"product": self.jar, "quantity": 1}])
        self.assertEqual(self.stock(), 0)

    def test_second_item_failing_rolls_back_stock_reserved_for_the_first(self):
        """The real point of wrapping create_order in one transaction: a
        cart with 2 lines where only the SECOND line is out of stock must
        not leave the first line's stock silently reserved."""
        with self.assertRaises(InsufficientStockError):
            self.place(items=[
                {"product": self.jar, "quantity": 2},
                {"product": self.small, "quantity": 11},  # only 10 in stock
            ])
        self.assertEqual(self.stock(self.jar), 10)
        self.assertEqual(self.stock(self.small), 10)
        self.assertEqual(Order.objects.count(), 0)

    def test_failure_after_stock_reserved_rolls_back_the_whole_order(self):
        """An exception after stock reservation (e.g. the payment step
        blowing up) must not leave stock consumed by an order that was
        never actually created."""
        with mock.patch("orders.services.Payment.objects.create", side_effect=RuntimeError("gateway down")):
            with self.assertRaises(RuntimeError):
                self.place(items=[{"product": self.jar, "quantity": 2}])
        self.assertEqual(self.stock(), 10)
        self.assertEqual(Order.objects.count(), 0)


class CancellationTests(OrderTestBase):
    def test_cancelling_restores_stock(self):
        order = self.place(items=[{"product": self.jar, "quantity": 4}])
        self.assertEqual(self.stock(), 6)
        ok, _ = cancel_order(order, cancelled_by=self.customer)
        self.assertTrue(ok)
        self.assertEqual(self.stock(), 10)

    def test_cancelling_a_mixed_cart_restores_stock_only_for_first_purchase_lines(self):
        CustomerBottleHolding.objects.create(customer=self.customer, product=self.jar, quantity=1)
        order = self.place(items=[
            {"product": self.jar, "quantity": 1},       # refill -- no stock was taken
            {"product": self.small, "quantity": 3},      # first purchase -- stock was taken
        ])
        self.assertEqual(self.stock(self.small), 7)
        cancel_order(order, cancelled_by=self.customer)
        self.assertEqual(self.stock(self.jar), 10)   # untouched throughout
        self.assertEqual(self.stock(self.small), 10)  # restored

    def test_cannot_cancel_once_staff_is_assigned(self):
        order = self.place(items=[{"product": self.jar, "quantity": 2}])
        order.status = Order.Status.ASSIGNED
        order.save()
        ok, message = cancel_order(order, cancelled_by=self.customer)
        self.assertFalse(ok)
        self.assertTrue(message)
        self.assertEqual(self.stock(), 8)  # stock NOT handed back

    def test_double_cancel_restores_stock_only_once(self):
        order = self.place(items=[{"product": self.jar, "quantity": 4}])
        cancel_order(order, cancelled_by=self.customer)
        cancel_order(order, cancelled_by=self.customer)
        self.assertEqual(self.stock(), 10)


class PromoCodeTests(OrderTestBase):
    def make_promo(self, **kwargs):
        defaults = dict(
            code="SAVE50", discount_amount=Decimal("50"), is_active=True,
            valid_from=timezone.now() - timedelta(days=1),
            valid_to=timezone.now() + timedelta(days=1),
        )
        defaults.update(kwargs)
        return PromoCode.objects.create(**defaults)

    def test_valid_code_reduces_the_total(self):
        self.make_promo()
        order = self.place()
        ok, _ = apply_promo_code(order, "SAVE50")
        self.assertTrue(ok)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("50"))
        self.assertEqual(order.total_amount, Decimal("250"))

    def test_expired_code_is_rejected(self):
        self.make_promo(valid_to=timezone.now() - timedelta(hours=1))
        order = self.place()
        ok, _ = apply_promo_code(order, "SAVE50")
        self.assertFalse(ok)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("0"))

    def test_usage_limit_is_enforced(self):
        promo = self.make_promo(max_uses=1)
        first = self.place()
        second = self.place()
        ok1, _ = apply_promo_code(first, "SAVE50")
        ok2, _ = apply_promo_code(second, "SAVE50")
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)

    def test_cancelling_returns_the_promo_use(self):
        promo = self.make_promo(max_uses=1)
        order = self.place()
        apply_promo_code(order, "SAVE50")
        cancel_order(order, cancelled_by=self.customer)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 0)

    def test_discount_never_exceeds_the_order_total(self):
        self.make_promo(code="HUGE", discount_amount=Decimal("99999"))
        order = self.place()
        apply_promo_code(order, "HUGE")
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("0"))


class AdminCancelActionTests(OrderTestBase):
    """The admin 'Cancel selected orders' action must go through
    cancel_order() -- not just flip the status field -- so stock and promo
    usage actually get restored, the same as the customer-facing cancel."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username="admin1", phone="01900000001", password="adminpass123",
        )
        self.client.force_login(self.staff)

    def test_action_restores_stock_and_sets_status(self):
        order = self.place(items=[{"product": self.jar, "quantity": 3}])
        self.assertEqual(self.stock(), 7)

        response = self.client.post(
            reverse("admin:orders_order_changelist"),
            {"action": "cancel_selected_orders", "_selected_action": [str(order.pk)]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.stock(), 10)

    def test_status_field_is_not_directly_editable_in_the_change_form(self):
        order = self.place()
        response = self.client.get(reverse("admin:orders_order_change", args=[order.pk]))
        self.assertNotContains(response, 'name="status"')

    def test_action_skips_an_order_already_past_the_cancellable_stage(self):
        order = self.place(items=[{"product": self.jar, "quantity": 2}])
        order.status = Order.Status.ASSIGNED
        order.save()

        self.client.post(
            reverse("admin:orders_order_changelist"),
            {"action": "cancel_selected_orders", "_selected_action": [str(order.pk)]},
            follow=True,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)  # untouched
        self.assertEqual(self.stock(), 8)  # stock NOT restored


class DestructiveActionsRequirePostTests(OrderTestBase):
    """A plain link (or a crawler, or browser prefetch) must not be able to
    cancel an order or re-place a reorder just by fetching a URL."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.customer)

    def test_cancel_rejects_get(self):
        order = self.place()
        response = self.client.get(reverse("orders:order_cancel", args=[order.pk]))
        self.assertEqual(response.status_code, 405)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)

    def test_cancel_accepts_post(self):
        order = self.place()
        self.client.post(reverse("orders:order_cancel", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_reorder_rejects_get(self):
        order = self.place()
        response = self.client.get(reverse("orders:order_reorder", args=[order.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Order.objects.count(), 1)

    def test_customer_cannot_open_someone_elses_order(self):
        other = User.objects.create_user(username="01800000002", phone="01800000002", password="x")
        other_address = Address.objects.create(user=other, full_address="Elsewhere")
        foreign = create_order(
            customer=other, address=other_address, items=[{"product": self.jar, "quantity": 1}],
            payment_method=Order.PaymentMethod.COD,
        )
        response = self.client.get(reverse("orders:order_detail", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
