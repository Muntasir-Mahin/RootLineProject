from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Product

from .forms import ProductForm


@login_required
def add_product_view(request):
    if not request.user.seller_approved:
        return redirect('profile')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)

        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            return redirect('seller_dashboard')

    else:
        form = ProductForm()

    return render(request, 'products/add_product.html', {'form': form})


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
        {'products': products}
    )

@login_required
def edit_product_view(request, product_id):
    if not request.user.seller_approved:
        return redirect('profile')

    product = Product.objects.get(
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
        form = ProductForm(instance=product)

    return render(
        request,
        'products/edit_product.html',
        {
            'form': form,
            'product': product
        }
    )

@login_required
def delete_product_view(request, product_id):
    if not request.user.seller_approved:
        return redirect('profile')

    product = Product.objects.get(
        id=product_id,
        seller=request.user
    )

    if request.method == 'POST':
        product.delete()
        return redirect('my_products')

    return render(
        request,
        'products/delete_product.html',
        {'product': product}
    )

@login_required
def product_detail_view(request, product_id):
    if not request.user.seller_approved:
        return redirect('profile')

    product = get_object_or_404(
        Product,
        id=product_id,
        seller=request.user
    )

    return render(
        request,
        'products/product_detail.html',
        {'product': product}
    )

def marketplace_view(request):
    products = Product.objects.filter(
        verification_status='verified',
        is_available=True,
        stock_quantity__gt=0
    ).order_by('-created_at')

    return render(
        request,
        'products/marketplace.html',
        {'products': products}
    )

def marketplace_product_detail_view(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
        verification_status='verified',
        is_available=True,
        stock_quantity__gt=0
    )

    return render(
        request,
        'products/marketplace_product_detail.html',
        {'product': product}
    )