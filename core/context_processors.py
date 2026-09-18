def notifications(request):
    if not request.user.is_authenticated:
        return {}
    unread = request.user.notifications.filter(is_read=False).order_by("-created_at")[:5]
    context = {
        "nav_notifications": unread,
        "nav_unread_count": request.user.notifications.filter(is_read=False).count(),
    }

    from accounts.models import Role

    if request.user.is_superuser or request.user.role in (
        Role.ADMIN, Role.OPERATIONS_MANAGER, Role.DELIVERY_MANAGER, Role.ACCOUNTANT,
    ):
        from orders.models import Order

        context["nav_unassigned_count"] = Order.objects.filter(
            status__in=[Order.Status.CREATED, Order.Status.CONFIRMED], assigned_staff__isnull=True
        ).count()

    return context
