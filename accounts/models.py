from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    seller_requested = models.BooleanField(default=False)
    seller_approved = models.BooleanField(default=False)

    def __str__(self):
        return self.username