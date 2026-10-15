from django.contrib.admin.apps import AdminConfig


class OwnerAdminConfig(AdminConfig):
    default_site = 'rootline.admin_site.OwnerAdminSite'

    def ready(self):
        super().ready()
        # Register after Django has discovered auth's built-in GroupAdmin.
        from django.contrib import admin
        from django.contrib.auth.models import Group
        from dashboard.group_admin import RoleGroupAdmin

        admin.site.unregister(Group)
        admin.site.register(Group, RoleGroupAdmin)
