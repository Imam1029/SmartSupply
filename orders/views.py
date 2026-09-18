from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.core.serializers.json import DjangoJSONEncoder
import json

from accounts.models import OTP, Address, Role
from bottles.models import CustomerBottleHolding
from catalog.models import Product
from core.utils import log_action, send_otp

from .cart import Cart
from .forms import AdminPlaceOrderForm, GuestOrderForm, GuestOTPForm, OrderCreateForm, SubscriptionForm
from .models import Order, Subscription
from .services import InsufficientStockError, cancel_order, create_order, has_conflicting_active_subscription

User = get_user_model()


def _can_place_phone_orders(user):
    return user.is_authenticated and (
        user.is_superuser or user.role in (Role.ADMIN, Role.OPERATIONS_MANAGER, Role.DELIVERY_MANAGER)
    )


@login_required
def cart_view(request):
    cart = Cart(request)
    lines = cart.line_items()
    water_total = sum(l["water_subtotal"] for l in lines)
    bottle_total = sum(l["bottle_subtotal"] for l in lines)
    return render(request, "orders/cart.html", {
        "lines": lines, "water_total": water_total, "bottle_total": bottle_total,
        "grand_total_estimate": water_total + bottle_total,
    })


@login_required
def cart_add_view(request):
    if request.method != "POST":
        return redirect("catalog:product_list")
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    quantity = max(1, int(request.POST.get("quantity", 1) or 1))
    Cart(request).add(product.pk, quantity)
    messages.success(request, f"{product.name} কার্টে যোগ করা হয়েছে।")
    return redirect(request.META.get("HTTP_REFERER") or "orders:cart")


@login_required
def cart_update_view(request, product_id):
    if request.method == "POST":
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        Cart(request).set_quantity(product_id, quantity)
    return redirect("orders:cart")


@login_required
def cart_remove_view(request, product_id):
    if request.method == "POST":
        Cart(request).remove(product_id)
        messages.info(request, "পণ্যটি কার্ট থেকে সরানো হয়েছে।")
    return redirect("orders:cart")


@login_required
def order_create_view(request):
    """Checkout -- reads items from the session cart (orders/cart.py), not
    a single product+quantity field, since an order can now hold multiple
    products. Redirects to the cart page if it's empty rather than showing
    a checkout form with nothing to check out."""
    if not request.user.addresses.exists():
        messages.warning(request, "অর্ডার করার আগে অন্তত একটি ডেলিভারি ঠিকানা যোগ করুন।")
        return redirect("accounts:addresses")

    cart = Cart(request)
    lines = cart.line_items()
    if not lines:
        messages.info(request, "আপনার কার্ট খালি -- অর্ডার করার আগে কিছু পণ্য যোগ করুন।")
        return redirect("catalog:product_list")

    if request.method == "POST":
        form = OrderCreateForm(request.POST, user=request.user)
        if form.is_valid():
            items = [{"product": line["product"], "quantity": line["quantity"]} for line in lines]
            try:
                order = create_order(
                    customer=request.user,
                    address=form.cleaned_data["address"],
                    items=items,
                    payment_method=form.cleaned_data["payment_method"],
                    is_express=form.cleaned_data["is_express"],
                    promo_code=form.cleaned_data.get("promo_code"),
                )
            except InsufficientStockError as e:
                messages.error(request, str(e.message) if hasattr(e, "message") else str(e))
            else:
                cart.clear()
                if getattr(order, "_promo_message", ""):
                    messages.info(request, order._promo_message)
                payment = getattr(order, "payment", None)
                if payment and payment.method in (Order.PaymentMethod.BKASH, Order.PaymentMethod.NAGAD):
                    return redirect("payments:gateway_demo", pk=payment.pk)
                messages.success(request, f"অর্ডার তৈরি হয়েছে! Order ID: {order.order_uid}")
                return redirect("orders:order_detail", pk=order.pk)
    else:
        form = OrderCreateForm(user=request.user)

    # Phase 2 duplicate-order alert: warn (don't block) if an active
    # subscription already covers a product in the cart.
    subscribed_product_ids = set(
        request.user.subscriptions.filter(is_active=True).values_list("product_id", flat=True)
    )
    if subscribed_product_ids & {line["product"].pk for line in lines}:
        messages.info(
            request,
            "আপনার কার্টে থাকা একটি বা একাধিক পণ্যের জন্য Auto-Refill Subscription চালু আছে। "
            "এখন manual order করলে duplicate delivery হতে পারে।",
        )

    # Precomputed per-line pricing preview (server-side, same rule
    # create_order() itself applies) -- simpler and less error-prone than
    # re-implementing the refill/first-purchase check in JS for what's now
    # potentially several lines instead of one.
    preview_lines = []
    running_total = 0
    for line in lines:
        product, qty = line["product"], line["quantity"]
        holding = CustomerBottleHolding.objects.filter(customer=request.user, product=product).first()
        held_qty = holding.quantity if holding else 0
        is_refill = held_qty >= qty
        water = product.water_price * qty
        bottle = 0 if is_refill else product.bottle_price * qty
        preview_lines.append({
            "product": product, "quantity": qty, "is_refill": is_refill,
            "water_amount": water, "bottle_amount": bottle, "line_total": water + bottle,
        })
        running_total += water + bottle

    return render(
        request,
        "orders/order_create.html",
        {"form": form, "preview_lines": preview_lines, "preview_total": running_total},
    )


ORDER_STATUS_STEPS = [
    (Order.Status.CREATED, "Order Created"),
    (Order.Status.CONFIRMED, "Admin Confirmed"),
    (Order.Status.ASSIGNED, "Staff Assigned"),
    (Order.Status.OUT_FOR_DELIVERY, "Out for Delivery"),
    (Order.Status.DELIVERED, "Delivered"),
]


@login_required
def order_detail_view(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    status_codes = [code for code, _ in ORDER_STATUS_STEPS]
    current_step_index = status_codes.index(order.status) if order.status in status_codes else -1
    timeline = [
        {"label": label, "done": i <= current_step_index}
        for i, (code, label) in enumerate(ORDER_STATUS_STEPS)
    ]
    return render(
        request,
        "orders/order_detail.html",
        {"order": order, "timeline": timeline, "is_terminal_exception": order.status in (Order.Status.FAILED, Order.Status.CANCELLED)},
    )


@login_required
@user_passes_test(_can_place_phone_orders)
def order_detail_admin_view(request, pk):
    """
    Same template as order_detail_view, but reachable by an admin/ops user
    for an order that isn't their own -- the normal order_detail_view is
    scoped to `customer=request.user`, which an admin who just placed a
    phone order on someone else's behalf isn't, so that view 404s for them.
    Discovered this while comparing notes with a parallel session that hit
    the same gap independently.
    """
    order = get_object_or_404(Order, pk=pk)
    status_codes = [code for code, _ in ORDER_STATUS_STEPS]
    current_step_index = status_codes.index(order.status) if order.status in status_codes else -1
    timeline = [
        {"label": label, "done": i <= current_step_index}
        for i, (code, label) in enumerate(ORDER_STATUS_STEPS)
    ]
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order, "timeline": timeline,
            "is_terminal_exception": order.status in (Order.Status.FAILED, Order.Status.CANCELLED),
            "hide_customer_actions": True,
        },
    )


@login_required
def order_receipt_view(request, pk):
    """Print-friendly receipt -- uses the browser's own Print / Save as PDF,
    so no extra PDF-generation dependency is needed server-side. Reachable
    by the owning customer OR an admin/ops staff (e.g. printing a receipt
    for a phone-order customer, or re-checking one after the fact) -- same
    reasoning as order_detail_admin_view below."""
    if _can_place_phone_orders(request.user):
        order = get_object_or_404(Order, pk=pk)
    else:
        order = get_object_or_404(Order, pk=pk, customer=request.user)
    return render(request, "orders/order_receipt.html", {"order": order})


@require_POST
@login_required
def order_reorder_view(request, pk):
    """One-click reorder: re-place a past order's items/address/payment
    method as a brand-new order, without the customer re-filling the whole
    form. Re-adds every item from the old order (not just one), matching
    the multi-item cart -- skips any item whose product has since been
    deactivated rather than failing the whole reorder."""
    old_order = get_object_or_404(Order, pk=pk, customer=request.user)
    items = [
        {"product": item.product, "quantity": item.quantity}
        for item in old_order.items.select_related("product").all()
        if item.product.is_active
    ]
    if not items:
        messages.error(request, "এই অর্ডারের পণ্যগুলো এখন আর পাওয়া যাচ্ছে না, তাই reorder করা যাচ্ছে না।")
        return redirect("orders:order_detail", pk=old_order.pk)

    try:
        new_order = create_order(
            customer=request.user,
            address=old_order.delivery_address,
            items=items,
            payment_method=old_order.payment_method
            if old_order.payment_method != Order.PaymentMethod.CORPORATE_POSTPAID
            else Order.PaymentMethod.COD,
        )
    except InsufficientStockError as e:
        messages.error(request, str(e.message) if hasattr(e, "message") else str(e))
        return redirect("orders:order_detail", pk=old_order.pk)

    payment = getattr(new_order, "payment", None)
    if payment and payment.method in (Order.PaymentMethod.BKASH, Order.PaymentMethod.NAGAD):
        return redirect("payments:gateway_demo", pk=payment.pk)
    messages.success(request, f"আগের অর্ডারের মতোই নতুন অর্ডার তৈরি হয়েছে! Order ID: {new_order.order_uid}")
    return redirect("orders:order_detail", pk=new_order.pk)


@require_POST
@login_required
def order_cancel_view(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    success, message = cancel_order(order, cancelled_by=request.user)
    (messages.success if success else messages.error)(request, message)
    return redirect("orders:order_detail", pk=order.pk)


@login_required
def order_list_view(request):
    from django.core.paginator import Paginator

    from .models import Order

    all_orders = request.user.orders.all()

    status_filter = request.GET.get("status", "").upper()
    filter_map = {
        "PENDING": [Order.Status.CREATED, Order.Status.CONFIRMED, Order.Status.ASSIGNED, Order.Status.OUT_FOR_DELIVERY],
        "DELIVERED": [Order.Status.DELIVERED],
        "CANCELLED": [Order.Status.CANCELLED, Order.Status.FAILED],
    }
    if status_filter in filter_map:
        all_orders = all_orders.filter(status__in=filter_map[status_filter])

    paginator = Paginator(all_orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"page_obj": page_obj, "status_filter": status_filter})


# ---------------------------------------------------------------------------
# Self-service subscription management (Phase 2 auto-refill)
# ---------------------------------------------------------------------------

@login_required
def subscription_list_view(request):
    subscriptions = request.user.subscriptions.select_related("product", "address").order_by("-is_active", "next_run_date")
    return render(request, "orders/subscription_list.html", {"subscriptions": subscriptions})


@login_required
def subscription_create_view(request):
    if not request.user.addresses.exists():
        messages.warning(request, "Subscription তৈরি করার আগে অন্তত একটি ডেলিভারি ঠিকানা যোগ করুন।")
        return redirect("accounts:addresses")

    initial = {}
    product_id = request.GET.get("product")
    if product_id:
        initial["product"] = product_id

    if request.method == "POST":
        form = SubscriptionForm(request.POST, user=request.user)
        if form.is_valid():
            from datetime import timedelta

            from django.utils import timezone

            sub = Subscription.objects.create(
                customer=request.user,
                product=form.cleaned_data["product"],
                address=form.cleaned_data["address"],
                interval=form.cleaned_data["interval"],
                custom_days=form.cleaned_data.get("custom_days"),
                is_active=True,
            )
            sub.next_run_date = timezone.localdate() + timedelta(days=sub.interval_days)
            sub.save(update_fields=["next_run_date"])
            log_action(request.user, "SUBSCRIPTION_CREATED", "Subscription", sub.pk)
            messages.success(request, "Subscription তৈরি হয়েছে। এখন থেকে নিয়মিত reminder/auto-refill এর আওতায় থাকবেন।")
            return redirect("orders:subscription_list")
    else:
        form = SubscriptionForm(user=request.user, initial=initial)

    return render(request, "orders/subscription_form.html", {"form": form})


@require_POST
@login_required
def subscription_toggle_view(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, customer=request.user)
    sub.is_active = not sub.is_active
    sub.save(update_fields=["is_active"])
    log_action(request.user, "SUBSCRIPTION_TOGGLED", "Subscription", sub.pk, is_active=sub.is_active)
    messages.success(request, "Subscription চালু করা হলো।" if sub.is_active else "Subscription বন্ধ (pause) করা হলো।")
    return redirect("orders:subscription_list")


@require_POST
@login_required
def subscription_skip_view(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, customer=request.user)
    new_date = sub.advance_next_run_date()
    log_action(request.user, "SUBSCRIPTION_SKIPPED", "Subscription", sub.pk, next_run_date=str(new_date))
    messages.success(request, f"পরবর্তী ডেলিভারি স্কিপ করা হয়েছে। এখন পরের ডেলিভারি: {new_date}")
    return redirect("orders:subscription_list")


@require_POST
@login_required
def subscription_delete_view(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, customer=request.user)
    sub.delete()
    messages.info(request, "Subscription মুছে ফেলা হয়েছে।")
    return redirect("orders:subscription_list")


# ---------------------------------------------------------------------------
# Guest checkout (no login required) -- collects name/phone/address inline,
# verifies phone via OTP, then creates a lightweight guest account behind
# the scenes so the order fits the same Order/Payment/Bottle models.
# ---------------------------------------------------------------------------

def guest_order_start_view(request):
    if request.method == "POST":
        form = GuestOrderForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data["phone"]
            request.session["guest_order_pending"] = {
                "full_name": form.cleaned_data["full_name"],
                "phone": phone,
                "house_name": form.cleaned_data["house_name"],
                "full_address": form.cleaned_data["full_address"],
                "landmark": form.cleaned_data["landmark"],
                "product_id": form.cleaned_data["product"].pk,
                "quantity": form.cleaned_data["quantity"],
                "payment_method": form.cleaned_data["payment_method"],
                "promo_code": form.cleaned_data.get("promo_code"),
            }
            send_otp(phone, OTP.Purpose.GUEST_ORDER)
            messages.info(request, "আপনার মোবাইলে OTP পাঠানো হয়েছে (dev mode: server console দেখুন)।")
            return redirect("orders:guest_order_verify")
    else:
        form = GuestOrderForm()

    # Guests don't have an account yet, so we can't know for certain
    # whether they already hold a bottle -- assume first purchase for the
    # price preview (true for the overwhelming majority of guest orders).
    guest_pricing = {
        p.pk: {"water_price": float(p.water_price), "bottle_price": float(p.bottle_price), "is_first_purchase": True}
        for p in Product.objects.filter(is_active=True)
    }
    return render(
        request,
        "orders/guest_order_start.html",
        {"form": form, "product_pricing_json": json.dumps(guest_pricing, cls=DjangoJSONEncoder)},
    )


def guest_order_verify_view(request):
    pending = request.session.get("guest_order_pending")
    if not pending:
        return redirect("orders:guest_order_start")

    if request.method == "POST":
        form = GuestOTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            otp = (
                OTP.objects.filter(phone=pending["phone"], purpose=OTP.Purpose.GUEST_ORDER, is_used=False)
                .order_by("-created_at")
                .first()
            )
            if otp and otp.is_valid() and otp.check_code(code):
                otp.is_used = True
                otp.save()

                # Re-use an existing account for this phone if one already
                # exists (e.g. a former guest, or a registered customer who
                # checked out as guest); otherwise create a new guest user.
                user, created = User.objects.get_or_create(
                    phone=pending["phone"],
                    defaults={
                        "username": pending["phone"],
                        "first_name": pending["full_name"],
                        "role": Role.CUSTOMER,
                        "is_guest": True,
                        "is_phone_verified": True,
                    },
                )
                if created:
                    user.set_unusable_password()
                    user.save()
                elif not user.is_phone_verified:
                    user.is_phone_verified = True
                    user.save()

                address = Address.objects.create(
                    user=user,
                    label="Guest Order Address",
                    house_name=pending.get("house_name", ""),
                    full_address=pending["full_address"],
                    landmark=pending.get("landmark", ""),
                    is_default=not user.addresses.exists(),
                )

                from catalog.models import Product

                product = Product.objects.get(pk=pending["product_id"])
                try:
                    order = create_order(
                        customer=user,
                        address=address,
                        items=[{"product": product, "quantity": pending["quantity"]}],
                        payment_method=pending["payment_method"],
                        promo_code=pending.get("promo_code"),
                    )
                except InsufficientStockError as e:
                    messages.error(request, str(e.message) if hasattr(e, "message") else str(e))
                    return redirect("orders:guest_order_start")

                del request.session["guest_order_pending"]

                # Log the guest in so they can track this order; a real
                # password can be set later from the dashboard if they want
                # a full account.
                auth_login(request, user)

                if getattr(order, "_promo_message", ""):
                    messages.info(request, order._promo_message)
                payment = getattr(order, "payment", None)
                if payment and payment.method in (Order.PaymentMethod.BKASH, Order.PaymentMethod.NAGAD):
                    return redirect("payments:gateway_demo", pk=payment.pk)
                messages.success(request, f"অর্ডার তৈরি হয়েছে! Order ID: {order.order_uid}")
                return redirect("orders:order_detail", pk=order.pk)
            messages.error(request, "OTP সঠিক নয় বা মেয়াদ শেষ হয়ে গেছে।")
    else:
        form = GuestOTPForm()
    return render(request, "orders/guest_order_verify.html", {"form": form, "phone": pending["phone"]})


@login_required
@user_passes_test(_can_place_phone_orders)
def admin_place_order_view(request):
    """
    Admin/Staff-placed order -- for a customer who called in rather than
    using the app/site themselves. No OTP step: the staff member taking the
    call is the one vouching for the customer's identity, so this trades
    that verification step for `Order.placed_by` recording exactly who
    entered it, for accountability.
    """
    if request.method == "POST":
        form = AdminPlaceOrderForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data["phone"]
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "username": phone,
                    "first_name": form.cleaned_data["full_name"],
                    "role": Role.CUSTOMER,
                    "is_guest": True,
                    "is_phone_verified": False,  # staff vouched, not the customer's own OTP
                },
            )
            if created:
                user.set_unusable_password()
                user.save()

            existing_address = form.cleaned_data.get("use_existing_address")
            if existing_address:
                address = existing_address
            else:
                address = Address.objects.create(
                    user=user,
                    label="Phone Order Address",
                    house_name=form.cleaned_data.get("house_name", ""),
                    full_address=form.cleaned_data["full_address"],
                    landmark=form.cleaned_data.get("landmark", ""),
                    is_default=not user.addresses.exists(),
                )

            try:
                order = create_order(
                    customer=user,
                    address=address,
                    items=[{"product": form.cleaned_data["product"], "quantity": form.cleaned_data["quantity"]}],
                    payment_method=form.cleaned_data["payment_method"],
                    is_express=form.cleaned_data["is_express"],
                    promo_code=form.cleaned_data.get("promo_code"),
                )
            except InsufficientStockError as e:
                messages.error(request, str(e.message) if hasattr(e, "message") else str(e))
                return redirect("orders:admin_place_order")

            order.placed_by = request.user
            order.status = Order.Status.CONFIRMED  # staff already confirmed details on the call
            order.save(update_fields=["placed_by", "status"])
            log_action(request.user, "PHONE_ORDER_PLACED", "Order", order.pk, for_customer=phone)

            if getattr(order, "_promo_message", ""):
                messages.info(request, order._promo_message)
            messages.success(request, f"{user.get_full_name() or phone}-এর জন্য অর্ডার {order.order_uid} বসানো হলো।")
            return redirect("orders:order_detail_admin", pk=order.pk)
    else:
        form = AdminPlaceOrderForm()

    return render(request, "orders/admin_place_order.html", {"form": form})


TRACKABLE_STATUSES = (Order.Status.ASSIGNED, Order.Status.OUT_FOR_DELIVERY)


@login_required
def order_track_view(request, pk):
    """
    Customer-facing live tracking page -- reuses the GPSPing data staff
    devices already post (delivery/api_views.py::gps_ping_view, Phase 2),
    just adds a customer-visible map for it. Only meaningful once a staff
    member is actually assigned and out delivering; before/after that
    window there's no live position to show, so the view degrades to a
    static status message instead of an empty map.
    """
    order = get_object_or_404(Order, pk=pk, customer=request.user)
    return render(request, "orders/order_track.html", {"order": order, "is_trackable": order.status in TRACKABLE_STATUSES})


@login_required
def order_track_data_view(request, pk):
    """JSON endpoint the tracking page polls for the assigned staff's
    latest position. Scoped to the order's own customer -- never exposes a
    staff member's location to anyone but the specific customer they're
    currently delivering to."""
    from django.http import JsonResponse
    from delivery.models import GPSPing

    order = get_object_or_404(Order, pk=pk, customer=request.user)
    if order.status not in TRACKABLE_STATUSES or not order.assigned_staff_id:
        return JsonResponse({"available": False})

    ping = GPSPing.objects.filter(staff_id=order.assigned_staff_id).order_by("-recorded_at").first()
    if not ping:
        return JsonResponse({"available": False})

    return JsonResponse({
        "available": True,
        "latitude": float(ping.latitude),
        "longitude": float(ping.longitude),
        "recorded_at": ping.recorded_at.isoformat(),
        "staff_name": order.assigned_staff.get_full_name() or "Delivery Staff",
    })
