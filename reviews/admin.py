from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):

    list_display = (
        'product',
        'buyer',
        'rating',
        'created_at'
    )