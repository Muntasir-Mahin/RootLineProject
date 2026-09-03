from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('RootLine Information', {
            'fields': (
                'phone_number',
                'address',
                'seller_requested',
                'seller_approved',
            )
        }),
    )


admin.site.register(User, CustomUserAdmin)