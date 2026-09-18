from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/", views.cart_add_view, name="cart_add"),
    path("cart/<int:product_id>/update/", views.cart_update_view, name="cart_update"),
    path("cart/<int:product_id>/remove/", views.cart_remove_view, name="cart_remove"),
    path("new/", views.order_create_view, name="order_create"),
    path("guest/", views.guest_order_start_view, name="guest_order_start"),
    path("guest/verify/", views.guest_order_verify_view, name="guest_order_verify"),
    path("admin/place/", views.admin_place_order_view, name="admin_place_order"),
    path("admin/<int:pk>/", views.order_detail_admin_view, name="order_detail_admin"),
    path("", views.order_list_view, name="order_list"),
    path("<int:pk>/", views.order_detail_view, name="order_detail"),
    path("<int:pk>/receipt/", views.order_receipt_view, name="order_receipt"),
    path("<int:pk>/track/", views.order_track_view, name="order_track"),
    path("<int:pk>/track/data/", views.order_track_data_view, name="order_track_data"),
    path("<int:pk>/reorder/", views.order_reorder_view, name="order_reorder"),
    path("<int:pk>/cancel/", views.order_cancel_view, name="order_cancel"),
    path("subscriptions/", views.subscription_list_view, name="subscription_list"),
    path("subscriptions/new/", views.subscription_create_view, name="subscription_create"),
    path("subscriptions/<int:pk>/toggle/", views.subscription_toggle_view, name="subscription_toggle"),
    path("subscriptions/<int:pk>/skip/", views.subscription_skip_view, name="subscription_skip"),
    path("subscriptions/<int:pk>/delete/", views.subscription_delete_view, name="subscription_delete"),
]
