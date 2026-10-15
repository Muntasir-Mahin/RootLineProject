from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from dashboard.permissions import ROLES


class Command(BaseCommand):
    help = 'Create the Finance, Support and Catalogue groups without granting Django admin permissions.'

    def handle(self, *args, **options):
        for name in ROLES:
            _, created = Group.objects.get_or_create(name=name)
            self.stdout.write(f'{name}: {"created" if created else "already exists"}')
