from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from products.models import Product
from .models import Wishlist



@login_required
def add_wishlist(request, product_id):

    product = get_object_or_404(
        Product,
        id=product_id
    )


    Wishlist.objects.get_or_create(
        user=request.user,
        product=product
    )


    return redirect(
        'marketplace_product_detail',
        product_id=product.id
    )



@login_required
def remove_wishlist(request, product_id):

    Wishlist.objects.filter(
        user=request.user,
        product_id=product_id
    ).delete()


    return redirect(
        'my_wishlist'
    )



@login_required
def my_wishlist(request):

    wishlist = Wishlist.objects.filter(
        user=request.user
    ).select_related(
        'product'
    )


    return render(
        request,
        'wishlist/my_wishlist.html',
        {
            'wishlist': wishlist
        }
    )