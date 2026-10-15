from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from dashboard.audit import DecisionError
from payments.services import confirm_delivery
from products.models import Product
from reviews.models import Review
from .forms import CheckoutForm
from .models import Cart, CartItem, Order
from .services import CheckoutUnavailable, checkout_cart, fixed_purchase_blocked, update_seller_order


def cart_quantity(value):
    return forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01')
    ).clean(value)


@login_required
def add_to_cart_view(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
        verification_status='verified',
        is_available=True,
        selling_type__in=['fixed', 'both'],
        price__isnull=False,
    )

    if product.seller_id == request.user.id:
        messages.error(request, 'You cannot buy your own product.')
        return redirect('marketplace_product_detail', product_id=product.id)

    if fixed_purchase_blocked(product.pk):
        messages.error(request, 'Fixed-price purchases are paused until this auction is settled.')
        return redirect('marketplace_product_detail', product_id=product.pk)

    if request.method == 'POST':
        try:
            quantity = cart_quantity(request.POST.get('quantity', '1'))
        except forms.ValidationError:
            return redirect('marketplace_product_detail', product_id=product.id)

        if quantity <= 0:
            return redirect('marketplace_product_detail', product_id=product.id)

        cart, created = Cart.objects.get_or_create(user=request.user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )

        if not created:
            new_quantity = cart_item.quantity + quantity

            if new_quantity <= product.stock_quantity:
                cart_item.quantity = new_quantity
                cart_item.save()

        else:
            if quantity > product.stock_quantity:
                cart_item.delete()

        return redirect('cart')

    return redirect('marketplace_product_detail', product_id=product.id)

@login_required
def cart_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)

    cart_items = cart.items.select_related('product')

    total_price = Decimal('0.00')

    for item in cart_items:
        if item.product.price:
            total_price += item.product.price * item.quantity

    return render(
        request,
        'orders/cart.html',
        {
            'cart': cart,
            'cart_items': cart_items,
            'total_price': total_price,
        }
    )

@login_required
def update_cart_item_view(request, item_id):
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )

    if request.method == 'POST':
        try:
            quantity = cart_quantity(request.POST.get('quantity', '1'))
        except forms.ValidationError:
            return redirect('cart')

        if quantity <= 0:
            return redirect('cart')

        if quantity <= cart_item.product.stock_quantity:
            cart_item.quantity = quantity
            cart_item.save()

    return redirect('cart')

@login_required
def remove_cart_item_view(request, item_id):
    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )

    if request.method == 'POST':
        cart_item.delete()

    return redirect('cart')

@login_required
def checkout_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)

    cart_items = cart.items.select_related(
        'product',
        'product__seller'
    )

    if not cart_items.exists():
        return redirect('cart')

    if cart_items.filter(product__seller=request.user).exists():
        messages.error(request, 'Remove your own products from the cart before checking out.')
        return redirect('cart')

    initial_data = {
        'recipient_name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
        'phone_number': request.user.phone_number,
        'delivery_address': request.user.address,
    }

    if request.method == 'POST':
        form = CheckoutForm(request.POST)

        if form.is_valid():

            try:
                created_orders = checkout_cart(cart.pk, request.user, form.cleaned_data)
            except CheckoutUnavailable as error:
                messages.error(request, str(error))
                return redirect('cart')
            request.session['latest_order_ids'] = [order.pk for order in created_orders]

            return redirect('order_success')

    else:
        form = CheckoutForm(initial=initial_data)

    total_price = Decimal('0.00')

    for item in cart_items:
        if item.product.price:
            total_price += item.product.price * item.quantity

    return render(
        request,
        'orders/checkout.html',
        {
            'form': form,
            'cart_items': cart_items,
            'total_price': total_price,
        }
    )

@login_required
def order_success_view(request):
    order_ids = request.session.get('latest_order_ids', [])

    orders = Order.objects.filter(
        id__in=order_ids,
        buyer=request.user
    ).prefetch_related('items')

    return render(
        request,
        'orders/order_success.html',
        {'orders': orders}
    )

@login_required
def my_orders_view(request):

    orders = Order.objects.filter(
        buyer=request.user
    ).prefetch_related(
        'items'
    ).order_by('-created_at')


    for order in orders:

        for item in order.items.all():

            item.has_review = Review.objects.filter(
                buyer=request.user,
                product=item.product,
                order=order
            ).exists()


    return render(
        request,
        'orders/my_orders.html',
        {
            'orders': orders
        }
    )

@login_required
def seller_orders_view(request):

    if not request.user.seller_approved:
        return redirect('profile')

    orders = Order.objects.filter(
        seller=request.user
    ).select_related('buyer').prefetch_related('items').order_by('-created_at')

    return render(
        request,
        'orders/seller_orders.html',
        {'orders': orders}
    )


@login_required
@require_POST
def update_order_status_view(request, order_id):
    if not request.user.seller_approved:
        return redirect('profile')
    get_object_or_404(Order, pk=order_id, seller=request.user)
    try:
        update_seller_order(order_id, actor=request.user, action=request.POST.get('action'))
    except DecisionError as error:
        messages.error(request, str(error))
    return redirect('seller_orders')


@login_required
@require_POST
def confirm_delivery_view(request, order_id):
    get_object_or_404(Order, pk=order_id, buyer=request.user)
    try:
        confirm_delivery(order_id, actor=request.user)
    except DecisionError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, 'Delivery confirmed and escrow released.')
    return redirect('my_orders')
