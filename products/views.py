from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Avg
from django.db import transaction

from .forms import ProductForm
from .models import Product

from reviews.models import Review
from bidding.services import finalize_auction
from wishlist.models import Wishlist
from orders.services import fixed_purchase_blocked


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
    ).order_by(
        '-created_at'
    )


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
@transaction.atomic
def edit_product_view(request, product_id):

    if not request.user.seller_approved:
        return redirect('profile')


    product = get_object_or_404(
        Product.objects.select_for_update(),
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

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    if request.method == "POST":

        product.is_available = False
        product.save(update_fields=['is_available'])

        return redirect('my_products')

    return render(
        request,
        'products/delete_product.html',
        {'product': product}
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
    ).prefetch_related(
        'reviews'
    )


    # -------------------------
    # SEARCH
    # -------------------------

    search_query = request.GET.get(
        'search'
    )

    if search_query:

        products = products.filter(
            name__icontains=search_query
        )


    # -------------------------
    # CATEGORY FILTER
    # -------------------------

    category = request.GET.get(
        'category'
    )

    if category:

        products = products.filter(
            category=category
        )


    # -------------------------
    # SELLING TYPE FILTER
    # -------------------------

    selling_type = request.GET.get(
        'selling_type'
    )

    if selling_type:

        products = products.filter(
            selling_type=selling_type
        )


    # -------------------------
    # PRICE FILTER
    # -------------------------

    min_price = request.GET.get(
        'min_price'
    )

    max_price = request.GET.get(
        'max_price'
    )


    for value, lookup in [(min_price, 'price__gte'), (max_price, 'price__lte')]:
        if value:
            try:
                price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0).clean(value)
            except forms.ValidationError:
                messages.error(request, 'Enter a valid non-negative price with at most two decimal places.')
            else:
                products = products.filter(**{lookup: price})

    # -------------------------
    # SORTING
    # -------------------------

    sort = request.GET.get('sort')

    if sort == 'low_price':

        products = products.order_by(
            'price'
        )


    elif sort == 'high_price':

        products = products.order_by(
            '-price'
        )


    elif sort == 'newest':

        products = products.order_by(
            '-created_at'
        )

    elif sort == 'rating':

        products = products.annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by(
            '-avg_rating'
        )
    # -------------------------
    # RATING
    # -------------------------

    for product in products:

        product.average_rating = product.reviews.aggregate(
            Avg('rating')
        )['rating__avg']


        product.review_count = product.reviews.count()



    return render(
        request,
        'products/marketplace.html',
        {
            'products': products,
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


    # Auction check

    auction = getattr(
        product,
        'auction',
        None
    )


    auction_is_active = False


    if auction:

        now = timezone.now()


        auction = finalize_auction(auction)

        auction_is_active = (
            auction.start_time <= now < auction.end_time
            and auction.status == 'active'
        )


    # ------------------------------
    # REVIEWS
    # ------------------------------

    reviews = product.reviews.select_related(
        'buyer'
    ).order_by(
        '-created_at'
    )

    seller_reviews = Review.objects.filter(
        product__seller=product.seller
    )

    seller_rating = seller_reviews.aggregate(
        Avg('rating')
    )['rating__avg']

    seller_review_count = seller_reviews.count()
    average_rating = reviews.aggregate(
        Avg('rating')
    )['rating__avg']


    return render(
        request,
        'products/marketplace_product_detail.html',
        {
            'product': product,

            'auction': auction,

            'auction_is_active': auction_is_active,

            'reviews': reviews,

            'average_rating': average_rating,
            'seller_rating': seller_rating,
            'seller_review_count': seller_review_count,
            'fixed_purchase_blocked': fixed_purchase_blocked(product.pk),
            'is_favourite': request.user.is_authenticated and Wishlist.objects.filter(
                user=request.user, product=product
            ).exists(),
        }
    )