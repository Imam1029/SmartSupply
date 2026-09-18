from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Role
from bottles.models import BottleInventory, CustomerBottleHolding, InventoryWriteOff
from core.models import Notification
from core.utils import log_action
from orders.forms import DeliveryExceptionForm
from orders.models import DeliveryException, Order
from payments.models import CashHandover, Payment

from .models import DeliveryIncentive

STAFF_INCENTIVE_PER_DELIVERY = 20  # BDT, flat rate for MVP


def _is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.role in (Role.ADMIN, Role.OPERATIONS_MANAGER, Role.DELIVERY_MANAGER, Role.ACCOUNTANT)
    )


@login_required
@user_passes_test(_is_admin)
def gps_tracking_view(request):
    """Simple Admin-facing GPS visibility page: latest known position per
    delivery staff member, each with a direct Google Maps link. A real
    live map (auto-refreshing markers) can replace this template later
    without touching the GPSPing model or the ping-collection API."""
    from delivery.models import GPSPing

    latest_by_staff = {}
    for ping in GPSPing.objects.select_related("staff").order_by("-recorded_at")[:500]:
        if ping.staff_id not in latest_by_staff:
            latest_by_staff[ping.staff_id] = ping
    return render(request, "delivery/gps_tracking.html", {"pings": latest_by_staff.values()})


@login_required
@user_passes_test(_is_admin)
def dashboard_summary_view(request):
    """Quick at-a-glance stats -- today's orders/revenue, pending deliveries,
    low-stock products, un-invoiced corporate exposure -- since Django
    Admin's default list views don't surface this on their own."""
    from django.db.models import Sum, Count, F
    from django.utils import timezone

    from catalog.models import Product
    from orders.models import Order
    from payments.models import CashHandover

    today = timezone.localdate()
    today_orders = Order.objects.filter(created_at__date=today)
    pending_delivery = Order.objects.exclude(
        status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED, Order.Status.FAILED]
    )
    low_stock_products = Product.objects.filter(is_active=True).filter(
        available_stock__lte=F("low_stock_threshold")
    )
    todays_handovers = CashHandover.objects.filter(handover_date=today)

    context = {
        "today_order_count": today_orders.count(),
        "today_revenue": today_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
        "pending_delivery_count": pending_delivery.count(),
        "delivered_today": Order.objects.filter(status=Order.Status.DELIVERED, updated_at__date=today).count(),
        "low_stock_products": low_stock_products,
        "cash_pending_count": todays_handovers.exclude(status=CashHandover.Status.VERIFIED).count(),
        "cash_pending_total": sum(
            (h.expected_amount - h.submitted_amount for h in todays_handovers.exclude(status=CashHandover.Status.VERIFIED)),
            0,
        ),
        "status_breakdown": Order.objects.values("status").annotate(count=Count("id")).order_by("-count"),
    }
    return render(request, "delivery/dashboard_summary.html", context)


@login_required
@user_passes_test(_is_admin)
def order_search_view(request):
    """Quick admin-side search by phone number or Order ID -- so a support
    call ("আমার অর্ডার কই?") doesn't require opening Django Admin and
    filtering manually. Searching by phone shows that customer's recent
    orders; a full/partial Order ID goes straight to the order."""
    from orders.models import Order

    query = request.GET.get("q", "").strip()
    results = Order.objects.none()
    matched_customer = None

    if query:
        # Looks like (part of) an order UUID -- try a direct/prefix match.
        if len(query) >= 4 and all(c in "0123456789abcdefABCDEF-" for c in query):
            results = Order.objects.filter(order_uid__istartswith=query.replace("-", ""))
            if not results.exists():
                results = Order.objects.filter(id=query) if query.isdigit() else Order.objects.none()

        if not results.exists():
            # Fall back to phone-number search.
            from accounts.validators import normalize_bd_phone

            phone = normalize_bd_phone(query) or query
            results = Order.objects.filter(customer__phone__icontains=phone)
            matched_customer = results.first().customer if results.exists() else None

    results = results.select_related("customer", "delivery_address").order_by("-created_at")[:30]
    return render(
        request, "delivery/order_search.html",
        {"query": query, "results": results, "matched_customer": matched_customer},
    )


@user_passes_test(_is_admin)
def unassigned_orders_view(request):
    """
    Quick Staff Assignment (part 1) -- orders that need a delivery staff
    assigned, in one list, instead of admins hunting through Django Admin's
    raw Order change-list and filtering manually.
    """
    orders = (
        Order.objects.filter(status__in=[Order.Status.CREATED, Order.Status.CONFIRMED], assigned_staff__isnull=True)
        .select_related("customer", "delivery_address")
        .order_by("created_at")
    )
    return render(request, "delivery/unassigned_orders.html", {"orders": orders})


@user_passes_test(_is_admin)
def assign_staff_view(request, pk):
    """
    Quick Staff Assignment (part 2) -- one click to assign a delivery staff
    member to an order (instead of the raw Django Admin change-form's
    assigned_staff dropdown + separate status field). Bumps status to
    ASSIGNED in the same action since "assigned but still shows as just
    confirmed" is a confusing intermediate state for daily ops to track.
    """
    order = get_object_or_404(Order, pk=pk)
    from django.db.models import Count, Q

    active_staff = get_user_model().objects.filter(role=Role.DELIVERY_STAFF, is_active=True).annotate(
        active_order_count=Count(
            "assigned_orders",
            filter=Q(assigned_orders__status__in=[Order.Status.ASSIGNED, Order.Status.OUT_FOR_DELIVERY]),
        )
    ).order_by("active_order_count", "first_name")

    if request.method == "POST":
        staff_id = request.POST.get("staff_id")
        staff = get_object_or_404(get_user_model(), pk=staff_id, role=Role.DELIVERY_STAFF)
        order.assigned_staff = staff
        if order.status in (Order.Status.CREATED, Order.Status.CONFIRMED):
            order.status = Order.Status.ASSIGNED
        order.save()
        log_action(request.user, "ORDER_ASSIGNED", "Order", order.pk, assigned_to=staff.get_full_name() or staff.phone)
        Notification.objects.create(
            user=order.customer,
            kind=Notification.Kind.STAFF_ASSIGNMENT,
            title="আপনার অর্ডার একজন ডেলিভারি স্টাফকে দেওয়া হয়েছে",
            message=f"অর্ডার {order.order_uid} শীঘ্রই ডেলিভারির জন্য বের হবে।",
        )
        messages.success(request, f"{staff.get_full_name() or staff.phone}-কে অর্ডার {order.order_uid} assign করা হলো।")
        return redirect("delivery:unassigned_orders")

    return render(request, "delivery/assign_staff.html", {"order": order, "active_staff": active_staff})


def _is_staff(user):
    return user.is_authenticated and user.role == Role.DELIVERY_STAFF


@login_required
@user_passes_test(_is_staff)
def staff_dashboard_view(request):
    today = timezone.localdate()
    assigned_orders = (
        Order.objects.filter(assigned_staff=request.user)
        .exclude(status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED])
        .select_related("customer", "delivery_address")
    )
    handover, _ = CashHandover.objects.get_or_create(
        staff=request.user, handover_date=today, defaults={"expected_amount": 0}
    )
    return render(
        request,
        "delivery/staff_dashboard.html",
        {"assigned_orders": assigned_orders, "handover": handover},
    )


@login_required
@user_passes_test(_is_staff)
def order_action_view(request, pk):
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    return render(request, "delivery/order_action.html", {"order": order})


@login_required
@user_passes_test(_is_staff)
def start_delivery_view(request, pk):
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    order.status = Order.Status.OUT_FOR_DELIVERY
    order.save()
    log_action(request.user, "ORDER_OUT_FOR_DELIVERY", "Order", order.pk)
    messages.success(request, "অর্ডার 'Out for Delivery' হিসেবে mark করা হলো।")
    return redirect("delivery:order_action", pk=order.pk)


@login_required
@user_passes_test(_is_staff)
def collect_empty_bottle_view(request, pk):
    """
    Staff collects empty bottle(s) from the customer and records condition
    -- aggregate exchange-count version, no per-unit bottle row involved.
    Loops over every item on the order (a multi-item cart order can have
    more than one product), collecting each item's own quantity; the
    condition selected applies to the whole batch collected on this visit
    (matches spec's "staff manually selects status" simplicity -- no
    per-bottle condition breakdown).
    """
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    condition = request.POST.get("condition", "GOOD")
    items = list(order.items.select_related("product").all())
    if not items:
        messages.error(request, "এই অর্ডারে collect করার মতো কোনো item নেই।")
        return redirect("delivery:order_action", pk=order.pk)

    if order.empties_collected_good or order.empties_collected_damaged:
        messages.info(request, "এই অর্ডারের bottle collection আগেই রেকর্ড করা হয়েছে।")
        return redirect("delivery:order_action", pk=order.pk)

    total_qty = 0
    with transaction.atomic():
        for item in items:
            qty = item.quantity
            total_qty += qty
            inventory, _ = BottleInventory.objects.get_or_create(product=item.product)
            holding, _ = CustomerBottleHolding.objects.get_or_create(customer=order.customer, product=item.product)

            if condition == "GOOD":
                inventory.available_count += qty
                inventory.save()
            else:
                reason = (
                    InventoryWriteOff.Reason.FIELD_COLLECTION_DAMAGED
                    if condition == "DAMAGED"
                    else InventoryWriteOff.Reason.FIELD_COLLECTION_UNUSABLE
                )
                inventory.damaged_count += qty
                inventory.save()
                # Customer no longer holds a usable bottle for this exchange --
                # their next order for this product goes back to
                # first-purchase pricing (spec: lost/damaged/unusable
                # bottle = customer's loss).
                holding.quantity = max(0, holding.quantity - qty)
                holding.save()
                InventoryWriteOff.objects.create(
                    product=item.product, quantity=qty, reason=reason,
                    note="Collected in the field; condition checked manually by staff (no photo evidence).",
                    related_order=order, performed_by=request.user,
                )

        if condition == "GOOD":
            order.empties_collected_good = total_qty
        else:
            order.empties_collected_damaged = total_qty
        order.save()

    log_action(request.user, "BOTTLE_COLLECTED", "Order", order.pk, condition=condition, quantity=total_qty)
    messages.success(request, "খালি বোতল collect ও condition check সম্পন্ন হয়েছে।")
    return redirect("delivery:order_action", pk=order.pk)


@login_required
@user_passes_test(_is_staff)
def deliver_full_bottle_view(request, pk):
    """
    Deliver full bottle(s) to the customer -- aggregate exchange-count
    version. Loops over every item on the order (multi-item cart support).
    Each item's own is_refill flag decides whether the customer's holding
    count goes up for that product (first-purchase) or stays the same
    (refill, straight swap) -- not the whole-order Order.order_type, which
    can now be MIXED across items. Either way, available_count drops by
    the quantity handed out for that product -- it came from company
    stock either way.
    """
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    items = list(order.items.select_related("product").all())
    if not items:
        messages.error(request, "এই অর্ডারে deliver করার মতো কোনো item নেই।")
        return redirect("delivery:order_action", pk=order.pk)

    if order.bottles_delivered:
        messages.info(request, "এই অর্ডারের bottle delivery আগেই রেকর্ড করা হয়েছে।")
        return redirect("delivery:order_action", pk=order.pk)

    total_qty = 0
    with transaction.atomic():
        for item in items:
            qty = item.quantity
            total_qty += qty
            inventory, _ = BottleInventory.objects.get_or_create(product=item.product)
            if inventory.available_count < qty:
                messages.warning(
                    request,
                    f"সতর্কতা: '{item.product.name}'-এর stock-এ মাত্র {inventory.available_count}টা bottle আছে, "
                    f"কিন্তু {qty}টা দিতে হবে -- তাও ডেলিভারি রেকর্ড করা হচ্ছে (stock ঋণাত্মক দেখাবে, reconcile করা দরকার)।",
                )
            inventory.available_count = max(0, inventory.available_count - qty)
            inventory.save()

            if not item.is_refill:
                holding, _ = CustomerBottleHolding.objects.get_or_create(customer=order.customer, product=item.product)
                holding.quantity += qty
                holding.save()

        order.bottles_delivered = total_qty
        order.save()

    log_action(request.user, "BOTTLE_DELIVERED", "Order", order.pk, quantity=total_qty)
    messages.success(request, "পূর্ণ বোতল ডেলিভারি সম্পন্ন হলো।")
    return redirect("delivery:order_action", pk=order.pk)


@login_required
@user_passes_test(_is_staff)
def complete_delivery_view(request, pk):
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    order.status = Order.Status.DELIVERED
    order.save()

    # Payment confirmation
    payment = getattr(order, "payment", None)
    if payment:
        if payment.method == Payment.Method.COD:
            payment.status = Payment.Status.COD_COLLECTED
        else:
            payment.status = Payment.Status.SUCCESS
        payment.save()

        # Cash reconciliation: track collected COD cash against today's handover
        if payment.method == Payment.Method.COD:
            today = timezone.localdate()
            handover, _ = CashHandover.objects.get_or_create(
                staff=request.user, handover_date=today, defaults={"expected_amount": 0}
            )
            handover.expected_amount += payment.amount
            handover.orders.add(order)
            handover.save()

    # Flat delivery incentive (Phase 2 feature, wired up simply here)
    DeliveryIncentive.objects.get_or_create(
        order=order, defaults={"staff": request.user, "amount": STAFF_INCENTIVE_PER_DELIVERY}
    )

    Notification.objects.create(
        user=order.customer,
        kind=Notification.Kind.DELIVERED,
        title="ডেলিভারি সম্পন্ন হয়েছে",
        message=f"আপনার অর্ডার {order.order_uid} সফলভাবে ডেলিভারি হয়েছে।",
    )
    log_action(request.user, "ORDER_DELIVERED", "Order", order.pk, amount=str(order.total_amount))
    messages.success(request, "ডেলিভারি সম্পন্ন হিসেবে mark করা হলো।")
    return redirect("delivery:staff_dashboard")


@login_required
@user_passes_test(_is_staff)
def report_exception_view(request, pk):
    order = get_object_or_404(Order, pk=pk, assigned_staff=request.user)
    if request.method == "POST":
        form = DeliveryExceptionForm(request.POST)
        if form.is_valid():
            DeliveryException.objects.create(
                order=order,
                reported_by=request.user,
                reason=form.cleaned_data["reason"],
                note=form.cleaned_data["note"],
            )
            order.status = Order.Status.FAILED
            order.save()
            Notification.objects.create(
                user=order.customer,
                kind=Notification.Kind.EXCEPTION_ALERT,
                title="ডেলিভারিতে সমস্যা হয়েছে",
                message=f"আপনার অর্ডার {order.order_uid} ডেলিভারিতে সমস্যা হয়েছে। আমরা শীঘ্রই যোগাযোগ করবো।",
            )
            log_action(request.user, "DELIVERY_EXCEPTION", "Order", order.pk, reason=form.cleaned_data["reason"])
            messages.info(request, "Exception রিপোর্ট করা হয়েছে, Admin review করবে।")
            return redirect("delivery:staff_dashboard")
    else:
        form = DeliveryExceptionForm()
    return render(request, "delivery/report_exception.html", {"form": form, "order": order})


@login_required
@user_passes_test(_is_staff)
def submit_cash_handover_view(request):
    today = timezone.localdate()
    handover, _ = CashHandover.objects.get_or_create(
        staff=request.user, handover_date=today, defaults={"expected_amount": 0}
    )
    if request.method == "POST":
        handover.submitted_amount = request.POST.get("submitted_amount") or 0
        handover.status = (
            CashHandover.Status.VERIFIED if handover.variance == 0 else CashHandover.Status.MISMATCH
        )
        handover.save()
        log_action(
            request.user, "CASH_HANDOVER_SUBMITTED", "CashHandover", handover.pk,
            expected=str(handover.expected_amount), submitted=str(handover.submitted_amount),
        )
        messages.success(request, "ক্যাশ হ্যান্ডওভার জমা দেওয়া হয়েছে।")
        return redirect("delivery:staff_dashboard")
    return render(request, "delivery/cash_handover.html", {"handover": handover})
