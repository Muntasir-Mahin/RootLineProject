from decimal import Decimal, InvalidOperation
from payments.models import Payment
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from products.models import Product
from .forms import CheckoutForm
from .models import Cart, CartItem, Order, OrderItem
from django.utils import timezone
from reviews.models import Review

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

    if request.method == 'POST':
        try:
            quantity = Decimal(request.POST.get('quantity', '1'))
        except InvalidOperation:
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
            quantity = Decimal(request.POST.get('quantity', '1'))
        except InvalidOperation:
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

    initial_data = {
        'recipient_name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
        'phone_number': request.user.phone_number,
        'delivery_address': request.user.address,
    }

    if request.method == 'POST':
        form = CheckoutForm(request.POST)

        if form.is_valid():

            # Check product availability and stock again
            for item in cart_items:
                product = item.product

                if (
                    product.verification_status != 'verified'
                    or not product.is_available
                    or product.selling_type not in ['fixed', 'both']
                    or product.price is None
                    or item.quantity > product.stock_quantity
                ):
                    return redirect('cart')

            with transaction.atomic():

                seller_items = {}

                # Group cart items by seller
                for item in cart_items:
                    seller_id = item.product.seller_id

                    if seller_id not in seller_items:
                        seller_items[seller_id] = []

                    seller_items[seller_id].append(item)

                created_orders = []

                # Create a separate order for each seller
                for seller_id, items in seller_items.items():

                    seller = items[0].product.seller

                    total_amount = Decimal('0.00')

                    for item in items:
                        total_amount += (
                            item.product.price * item.quantity
                        )

                    order = Order.objects.create(
                        buyer=request.user,
                        seller=seller,
                        recipient_name=form.cleaned_data['recipient_name'],
                        email=form.cleaned_data['email'],
                        phone_number=form.cleaned_data['phone_number'],
                        delivery_address=form.cleaned_data['delivery_address'],
                        payment_method=form.cleaned_data['payment_method'],
                        total_amount=total_amount,
                        status='pending'
                    )

                    Payment.objects.create(
                        order=order,
                        amount=total_amount,
                        payment_status='pending',
                        escrow_status='not_held'
                    )

                    created_orders.append(order)

                    for item in items:
                        product = item.product

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            product_name=product.name,
                            price=product.price,
                            quantity=item.quantity,
                            unit=product.unit
                        )

                        # Reduce stock
                        product.stock_quantity -= item.quantity

                        if product.stock_quantity <= 0:
                            product.stock_quantity = 0
                            product.is_available = False

                        product.save(
                            update_fields=[
                                'stock_quantity',
                                'is_available'
                            ]
                        )

                # Clear cart after order creation
                cart.items.all().delete()

                # Save newly created order IDs temporarily
                request.session['latest_order_ids'] = [
                    order.id for order in created_orders
                ]

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
def update_order_status_view(request, order_id):

    if not request.user.seller_approved:
        return redirect('profile')

    order = get_object_or_404(
        Order,
        id=order_id,
        seller=request.user
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if order.status == 'pending':

            if action == 'confirm':
                order.status = 'confirmed'
                order.save(update_fields=['status'])

            elif action == 'cancel':

                with transaction.atomic():

                    # Restore product stock
                    for item in order.items.select_related('product'):
                        product = item.product

                        product.stock_quantity += item.quantity
                        product.is_available = True

                        product.save(
                            update_fields=[
                                'stock_quantity',
                                'is_available'
                            ]
                        )

                    # Refund payment if buyer already paid
                    payment = Payment.objects.filter(
                        order=order
                    ).first()

                    if (
                        payment
                        and payment.payment_status == 'paid'
                        and payment.escrow_status == 'held'
                    ):
                        payment.payment_status = 'refunded'
                        payment.escrow_status = 'refunded'
                        payment.commission_amount = Decimal('0.00')
                        payment.seller_amount = Decimal('0.00')

                        payment.save(
                            update_fields=[
                                'payment_status',
                                'escrow_status',
                                'commission_amount',
                                'seller_amount',
                            ]
                        )

                    order.status = 'cancelled'
                    order.save(update_fields=['status'])

        elif order.status == 'confirmed':

            if action == 'ship':

                payment = Payment.objects.filter(
                    order=order
                ).first()

                if (
                        payment
                        and payment.payment_status == 'paid'
                        and payment.escrow_status == 'held'
                ):
                    order.status = 'shipped'
                    order.save(update_fields=['status'])

        return redirect('seller_orders')

    return redirect('seller_orders')

@login_required
def confirm_delivery_view(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        buyer=request.user
    )

    if request.method == 'POST':

        if order.status == 'shipped':

            payment = order.payment

            # Delivery only completes if payment is already held in escrow
            if (
                payment.payment_status == 'paid'
                and payment.escrow_status == 'held'
            ):

                with transaction.atomic():

                    commission = (
                        payment.amount * Decimal('0.05')
                    ).quantize(Decimal('0.01'))

                    seller_amount = (
                        payment.amount - commission
                    )

                    payment.commission_amount = commission
                    payment.seller_amount = seller_amount
                    payment.escrow_status = 'released'
                    payment.released_at = timezone.now()

                    payment.save(
                        update_fields=[
                            'commission_amount',
                            'seller_amount',
                            'escrow_status',
                            'released_at',
                        ]
                    )

                    order.status = 'delivered'
                    order.save(update_fields=['status'])

        return redirect('my_orders')

    return redirect('my_orders')