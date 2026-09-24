from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Avg

from .forms import ProductForm
from .models import Product

from reviews.models import Review


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

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    if request.method == "POST":

        product.is_available = False
        product.save()

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


    if min_price:

        products = products.filter(
            price__gte=min_price
        )


    if max_price:

        products = products.filter(
            price__lte=max_price
        )

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


        if (
            auction.start_time <= now < auction.end_time
            and auction.status == 'upcoming'
        ):

            auction.status = 'active'

            auction.save(
                update_fields=[
                    'status'
                ]
            )


        elif (
            now >= auction.end_time
            and auction.status == 'active'
        ):

            auction.status = 'ended'

            auction.save(
                update_fields=[
                    'status'
                ]
            )


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
        }
    )