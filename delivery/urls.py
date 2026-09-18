from django.urls import path

from . import api_views, views

app_name = "delivery"

urlpatterns = [
    path("", views.staff_dashboard_view, name="staff_dashboard"),
    path("orders/<int:pk>/", views.order_action_view, name="order_action"),
    path("orders/<int:pk>/start/", views.start_delivery_view, name="start_delivery"),
    path("orders/<int:pk>/collect-bottle/", views.collect_empty_bottle_view, name="collect_bottle"),
    path("orders/<int:pk>/deliver-bottle/", views.deliver_full_bottle_view, name="deliver_bottle"),
    path("orders/<int:pk>/complete/", views.complete_delivery_view, name="complete_delivery"),
    path("orders/<int:pk>/exception/", views.report_exception_view, name="report_exception"),
    path("cash-handover/", views.submit_cash_handover_view, name="cash_handover"),
    path("gps-tracking/", views.gps_tracking_view, name="gps_tracking"),
    path("dashboard-summary/", views.dashboard_summary_view, name="dashboard_summary"),
    path("search/", views.order_search_view, name="order_search"),
    path("unassigned-orders/", views.unassigned_orders_view, name="unassigned_orders"),
    path("orders/<int:pk>/assign/", views.assign_staff_view, name="assign_staff"),
    path("api/gps-ping/", api_views.gps_ping_view, name="api_gps_ping"),
    path("api/offline-sync/", api_views.offline_sync_view, name="api_offline_sync"),
]
