from django.urls import path
from .views import (
    add_to_cart_view,
    cart_view,
    update_cart_item_view,
    remove_cart_item_view,
    checkout_view,
    order_success_view,
    my_orders_view, seller_orders_view,
    update_order_status_view,confirm_delivery_view
)


urlpatterns = [
    path('cart/', cart_view, name='cart'),

    path(
        'cart/add/<int:product_id>/',
        add_to_cart_view,
        name='add_to_cart'
    ),
path(
    'cart/update/<int:item_id>/',
    update_cart_item_view,
    name='update_cart_item'
),

path(
    'cart/remove/<int:item_id>/',
    remove_cart_item_view,
    name='remove_cart_item'
),
path('checkout/', checkout_view, name='checkout'),
path(
    'success/',
    order_success_view,
    name='order_success'
),
path('my-orders/', my_orders_view, name='my_orders'),
path('seller-orders/', seller_orders_view, name='seller_orders'),
path(
    'seller-orders/<int:order_id>/status/',
    update_order_status_view,
    name='update_order_status'
),
path(
    'my-orders/<int:order_id>/confirm-delivery/',
    confirm_delivery_view,
    name='confirm_delivery'
),
]