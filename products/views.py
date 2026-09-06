from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ProductForm
from .models import Product


# --------------------------------------------------
# ADD PRODUCT
# --------------------------------------------------

@login_required
def add_product_view(request):

    if not request.user.seller_approved:
        return redirect('profile')

    if request.method == 'POST':
        form = ProductForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            product = form.save(commit=False)

            product.seller = request.user
            product.save()

            return redirect('seller_dashboard')

    else:
        form = ProductForm()

    return render(
        request,
        'products/add_product.html',
        {
            'form': form
        }
    )


# --------------------------------------------------
# SELLER'S PRODUCTS
# --------------------------------------------------

@login_required
def my_products_view(request):

    if not request.user.seller_approved:
        return redirect('profile')

    products = Product.objects.filter(
        seller=request.user
    ).order_by('-created_at')

    return render(
        request,
        'products/my_products.html',
        {
            'products': products
        }
    )


# --------------------------------------------------
# EDIT PRODUCT
# --------------------------------------------------

@login_required
def edit_product_view(request, product_id):

    if not request.user.seller_approved:
        return redirect('profile')

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    if request.method == 'POST':

        form = ProductForm(
            request.POST,
            request.FILES,
            instance=product
        )

        if form.is_valid():
            form.save()

            return redirect('my_products')

    else:
        form = ProductForm(
            instance=product
        )

    return render(
        request,
        'products/edit_product.html',
        {
            'form': form,
            'product': product
        }
    )


# --------------------------------------------------
# DELETE PRODUCT
# --------------------------------------------------

@login_required
def delete_product_view(request, product_id):

    if not request.user.seller_approved:
        return redirect('profile')

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    if request.method == 'POST':
        product.delete()

        return redirect('my_products')

    return render(
        request,
        'products/delete_product.html',
        {
            'product': product
        }
    )


# --------------------------------------------------
# SELLER PRODUCT DETAILS
# --------------------------------------------------

@login_required
def product_detail_view(request, product_id):

    if not request.user.seller_approved:
        return redirect('profile')

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    # Product-er auction ache kina
    auction = getattr(
        product,
        'auction',
        None
    )

    highest_bid = None
    bids = []

    if auction:

        highest_bid = auction.bids.select_related(
            'bidder'
        ).order_by(
            '-amount',
            'created_at'
        ).first()

        bids = auction.bids.select_related(
            'bidder'
        ).order_by(
            '-created_at'
        )

    return render(
        request,
        'products/product_detail.html',
        {
            'product': product,
            'auction': auction,
            'highest_bid': highest_bid,
            'bids': bids,
        }
    )


# --------------------------------------------------
# PUBLIC MARKETPLACE
# --------------------------------------------------

def marketplace_view(request):

    products = Product.objects.filter(
        verification_status='verified',
        is_available=True,
        stock_quantity__gt=0
    ).select_related(
        'seller'
    ).order_by(
        '-created_at'
    )

    return render(
        request,
        'products/marketplace.html',
        {
            'products': products
        }
    )


# --------------------------------------------------
# MARKETPLACE PRODUCT DETAILS
# --------------------------------------------------

def marketplace_product_detail_view(request, product_id):

    product = get_object_or_404(
        Product,
        id=product_id,
        verification_status='verified',
        is_available=True,
        stock_quantity__gt=0
    )

    # Product-er sathe auction ache kina
    auction = getattr(
        product,
        'auction',
        None
    )

    auction_is_active = False

    if auction:

        now = timezone.now()

        # Time onujayi status update
        if (
            auction.start_time <= now < auction.end_time
            and auction.status == 'upcoming'
        ):
            auction.status = 'active'

            auction.save(
                update_fields=['status']
            )

        elif (
            now >= auction.end_time
            and auction.status == 'active'
        ):
            auction.status = 'ended'

            auction.save(
                update_fields=['status']
            )

        auction_is_active = (
            auction.start_time <= now < auction.end_time
            and auction.status == 'active'
        )

    return render(
        request,
        'products/marketplace_product_detail.html',
        {
            'product': product,
            'auction': auction,
            'auction_is_active': auction_is_active,
        }
    )