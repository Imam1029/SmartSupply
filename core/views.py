from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control

from catalog.models import Product

from .models import Notification


def home_view(request):
    products = Product.objects.filter(is_active=True)[:8]
    return render(request, "core/home.html", {"products": products})


def offline_view(request):
    return render(request, "core/offline.html")


@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def service_worker_view(request):
    """
    Serves static/sw.js at the site root (/sw.js) instead of under /static/,
    since a service worker's control scope is limited to the directory it's
    served from -- this app needs to control the whole site, not just
    /static/. Reads straight off disk rather than through the staticfiles
    app so this works the same whether or not `collectstatic` has run yet.

    Explicitly uncacheable (unlike normal static assets) so a browser
    checking for service-worker updates always gets the latest version
    rather than a stale intermediary/browser cache.
    """
    sw_path = settings.BASE_DIR / "static" / "sw.js"
    with open(sw_path, "rb") as f:
        content = f.read()
    return HttpResponse(content, content_type="application/javascript")


@login_required
def mark_notification_read_view(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    return redirect(request.META.get("HTTP_REFERER", "core:home"))
