from django.urls import path
from . import views
from .schema import annotate_core

annotate_core(views)

urlpatterns=[
    path('health/',views.health),path('bootstrap/',views.bootstrap),
    path('auth/register/',views.register),path('auth/login/',views.login_view),path('auth/logout/',views.logout_view),
    path('catalog/products/',views.catalog),path('catalog/products/<slug:slug>/',views.catalog_detail),
    path('cart/',views.cart),path('checkout/',views.checkout),path('orders/',views.orders),path('orders/<uuid:pk>/',views.order_detail),path('orders/<uuid:pk>/cancel/',views.cancel_order),path('orders/<uuid:pk>/returns/',views.request_return),
    path('staff/orders/',views.staff_orders),path('staff/orders/<uuid:pk>/',views.staff_order_detail),path('staff/orders/<uuid:pk>/action/',views.staff_order_action),path('staff/returns/',views.staff_returns),path('staff/returns/<uuid:pk>/action/',views.staff_return_action),path('staff/refunds/',views.staff_refunds),path('staff/refunds/<uuid:pk>/confirm/',views.confirm_refund),
    path('staff/products/',views.staff_products),path('staff/products/<uuid:pk>/',views.staff_product_detail),path('staff/inventory/',views.staff_inventory),path('staff/users/',views.staff_users),path('staff/users/<int:pk>/',views.staff_user_detail),path('staff/settings/',views.staff_settings),path('staff/audit/',views.audit_events),
    path('payments/sslcommerz/ipn/',views.payment_ipn),path('payments/sslcommerz/return/',views.payment_return),
]
