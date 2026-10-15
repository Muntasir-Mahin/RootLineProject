from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from dashboard.admin import ServiceActionMixin
from dashboard.services import review_seller
from .models import User


@admin.register(User)
class CustomUserAdmin(ServiceActionMixin, UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('RootLine Information', {'fields': (
            'phone_number', 'address', 'seller_requested', 'seller_requested_at', 'seller_approved',
        )}),
    )
    readonly_fields = ('seller_requested', 'seller_requested_at', 'seller_approved')
    actions = ('approve_sellers', 'reject_sellers', 'revoke_sellers')

    @admin.action(description='Approve seller requests')
    def approve_sellers(self, request, queryset):
        self.run_service(request, queryset, review_seller, decision='approve')

    @admin.action(description='Reject seller requests')
    def reject_sellers(self, request, queryset):
        self.run_service(request, queryset, review_seller, decision='reject')

    @admin.action(description='Revoke seller approval')
    def revoke_sellers(self, request, queryset):
        self.run_service(request, queryset, review_seller, decision='revoke')
