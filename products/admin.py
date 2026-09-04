from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'seller',
        'category',
        'selling_type',
        'verification_status',
        'stock_quantity',
        'is_available',
    )

    list_filter = (
        'selling_type',
        'verification_status',
        'is_available',
        'category',
    )

    search_fields = (
        'name',
        'seller__username',
        'category',
    )