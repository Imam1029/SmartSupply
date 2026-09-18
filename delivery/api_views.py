import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Role
from orders.models import Order

from .models import GPSPing, OfflineSyncEvent


def _is_staff(user):
    return user.is_authenticated and user.role == Role.DELIVERY_STAFF


@login_required
@user_passes_test(_is_staff)
@require_POST
def gps_ping_view(request):
    """Staff mobile browser posts its current location every N seconds while
    on a delivery run. Admin can see the latest pings per staff in Admin."""
    try:
        data = json.loads(request.body)
        lat = data["latitude"]
        lng = data["longitude"]
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "latitude/longitude required"}, status=400)

    GPSPing.objects.create(staff=request.user, latitude=lat, longitude=lng)
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(_is_staff)
@require_POST
def offline_sync_view(request):
    """Bulk-accepts a batch of events a staff device queued while offline.

    Each event is idempotent on (staff, local_event_id) so replaying the
    same batch twice (e.g. a flaky retry) doesn't double-apply anything.
    This endpoint only *records* the events; it doesn't yet replay them
    against Order/BottleInventory state automatically -- that's flagged for
    manual admin review via sync_status=CONFLICT when related_order can't
    be resolved, which keeps the server authoritative.
    """
    try:
        payload = json.loads(request.body)
        events = payload["events"]
    except (KeyError, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "events[] required"}, status=400)

    accepted, conflicts = 0, 0
    for ev in events:
        related_order = None
        order_id = ev.get("related_order_id")
        if order_id:
            related_order = Order.objects.filter(pk=order_id, assigned_staff=request.user).first()

        obj, created = OfflineSyncEvent.objects.get_or_create(
            staff=request.user,
            local_event_id=ev["local_event_id"],
            defaults={
                "event_type": ev["event_type"],
                "related_order": related_order,
                "payload": ev.get("payload", {}),
                "device_reference": ev.get("device_reference", ""),
                "occurred_at": parse_datetime(ev["occurred_at"]) or timezone.now(),
            },
        )
        if not created:
            continue  # already synced earlier, idempotent no-op

        if order_id and related_order is None:
            obj.sync_status = OfflineSyncEvent.SyncStatus.CONFLICT
            obj.conflict_note = f"Order #{order_id} not found or not assigned to this staff member."
            conflicts += 1
        else:
            obj.sync_status = OfflineSyncEvent.SyncStatus.ACCEPTED
            accepted += 1
        obj.synced_at = timezone.now()
        obj.save()

    return JsonResponse({"ok": True, "accepted": accepted, "conflicts": conflicts})
