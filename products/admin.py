from django.contrib import admin

from dashboard.admin import ServiceActionMixin
from dashboard.services import review_product
from .models import Product


@admin.register(Product)
class ProductAdmin(ServiceActionMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'seller', 'selling_type', 'price', 'stock_quantity', 'verification_status', 'is_available')
    list_filter = ('selling_type', 'verification_status', 'is_available')
    search_fields = ('name', 'seller__username', 'category')
    readonly_fields = ('verification_status',)
    actions = ('verify_products', 'reject_products')

    @admin.action(description='Verify selected products')
    def verify_products(self, request, queryset):
        self.run_service(request, queryset, review_product, decision='verified')

    @admin.action(description='Reject selected products')
    def reject_products(self, request, queryset):
        self.run_service(request, queryset, review_product, decision='rejected')
