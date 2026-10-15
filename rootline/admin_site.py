from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied


class OwnerAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError('The Django admin is reserved for the owner.', code='invalid_login')


class OwnerAdminSite(AdminSite):
    login_form = OwnerAuthenticationForm
    site_header = 'RootLine owner administration'

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_staff and user.is_superuser

    def admin_view(self, view, cacheable=False):
        wrapped = super().admin_view(view, cacheable)

        def owner_view(request, *args, **kwargs):
            if request.user.is_authenticated and not self.has_permission(request):
                raise PermissionDenied('The Django admin is reserved for the owner.')
            return wrapped(request, *args, **kwargs)
        return owner_view

    def login(self, request, extra_context=None):
        if request.user.is_authenticated and not self.has_permission(request):
            raise PermissionDenied('The Django admin is reserved for the owner.')
        return super().login(request, extra_context)
