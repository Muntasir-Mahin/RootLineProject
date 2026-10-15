from functools import wraps

from django.core.exceptions import PermissionDenied

FINANCE = 'Finance'
SUPPORT = 'Support'
CATALOGUE = 'Catalogue'
ROLES = (FINANCE, SUPPORT, CATALOGUE)


def has_role(user, role=None):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.is_staff and (role is None or user.groups.filter(name=role).exists())


def staff_role_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, role):
                raise PermissionDenied('Active staff membership and the appropriate role are required.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
