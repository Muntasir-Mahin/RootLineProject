from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from products.models import Product
from orders.models import Order

from .models import Review
from .forms import ReviewForm

from django.db.models import Avg



@login_required
def add_review_view(request, product_id, order_id):

    product = get_object_or_404(
        Product,
        id=product_id
    )


    order = get_object_or_404(
        Order,
        id=order_id,
        buyer=request.user
    )


    # Only delivered order can review

    if order.status != 'delivered':
        return redirect('my_orders')


    # Check already reviewed

    if Review.objects.filter(
        buyer=request.user,
        product=product,
        order=order
    ).exists():

        return redirect(
            'marketplace_product_detail',
            product_id=product.id
        )


    if request.method == 'POST':

        form = ReviewForm(request.POST)


        if form.is_valid():

            review = form.save(commit=False)

            review.buyer = request.user
            review.product = product
            review.order = order

            review.save()


            return redirect(
                'marketplace_product_detail',
                product_id=product.id
            )


    else:

        form = ReviewForm()


    return render(
        request,
        'reviews/add_review.html',
        {
            'form': form,
            'product': product,
            'order': order,
        }
    )



@login_required
def seller_reviews_view(request):

    if not request.user.seller_approved:
        return redirect('profile')


    reviews = Review.objects.filter(
        product__seller=request.user
    ).select_related(
        'buyer',
        'product'
    ).order_by(
        '-created_at'
    )


    seller_rating = reviews.aggregate(
        Avg('rating')
    )['rating__avg']


    total_reviews = reviews.count()


    return render(
        request,
        'reviews/seller_reviews.html',
        {
            'reviews': reviews,
            'seller_rating': seller_rating,
            'total_reviews': total_reviews,
        }
    )