from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Round
from django.utils import timezone

from bidding.models import Auction
from payments.models import Payment
from products.models import Product
from .models import Cart, Order, OrderItem


class CheckoutUnavailable(Exception):
    """The cart changed or its products can no longer be purchased."""


def fixed_purchase_blocked(product_id):
    """Protect stock until a live auction or its winning checkout is settled."""
    return Auction.objects.filter(product_id=product_id, order__isnull=True).exclude(
        status='cancelled'
    ).filter(
        Q(status__in=['upcoming', 'active'], end_time__gt=timezone.now())
        | Q(winner__isnull=False)
        | Q(bids__isnull=False)
    ).exists()


def deduct_stock(product, quantity):
    """A conditional database update prevents lost updates and negative stock."""
    updated = Product.objects.filter(
        pk=product.pk,
        verification_status='verified',
        is_available=True,
        stock_quantity__gte=quantity,
    ).update(
        stock_quantity=Round(F('stock_quantity') - quantity, precision=2),
        is_available=Case(
            When(stock_quantity=quantity, then=Value(False)),
            default=F('is_available'),
        ),
    )
    if not updated:
        raise CheckoutUnavailable('A product is unavailable or has insufficient stock.')


@transaction.atomic
def checkout_cart(cart_id, buyer, checkout_data):
    # A cart lock serializes duplicate submissions. Product locks use a stable
    # order shared by stock writers; SQLite serializes writers with IMMEDIATE.
    cart = Cart.objects.select_for_update().get(pk=cart_id, user=buyer)
    items = list(cart.items.select_for_update().order_by('product_id'))
    if not items:
        raise CheckoutUnavailable('Your cart is empty.')

    products = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(
            pk__in=[item.product_id for item in items]
        ).order_by('pk')
    }
    seller_items = defaultdict(list)
    for item in items:
        product = products[item.product_id]
        if product.seller_id == buyer.pk:
            raise CheckoutUnavailable('You cannot buy your own product.')
        if (
            product.verification_status != 'verified'
            or not product.is_available
            or product.selling_type not in ['fixed', 'both']
            or product.price is None
            or item.quantity <= Decimal('0')
            or item.quantity > product.stock_quantity
        ):
            raise CheckoutUnavailable('A product is unavailable or has insufficient stock.')
        if fixed_purchase_blocked(product.pk):
            raise CheckoutUnavailable('Fixed-price purchases are paused until this auction is settled.')
        item.product = product
        seller_items[product.seller_id].append(item)

    orders = []
    for seller_id, items_for_seller in seller_items.items():
        total = sum((item.product.price * item.quantity for item in items_for_seller), Decimal('0'))
        order = Order.objects.create(
            buyer=buyer, seller_id=seller_id, total_amount=total,
            status='pending', **checkout_data,
        )
        Payment.objects.create(order=order, amount=total)
        for item in items_for_seller:
            deduct_stock(item.product, item.quantity)
            OrderItem.objects.create(
                order=order, product=item.product, product_name=item.product.name,
                price=item.product.price, quantity=item.quantity, unit=item.product.unit,
            )
        orders.append(order)

    cart.items.filter(pk__in=[item.pk for item in items]).delete()
    return orders
