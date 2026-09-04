from django.conf import settings
from django.db import models


class Product(models.Model):

    SELLING_TYPE_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('bidding', 'Bidding'),
        ('both', 'Fixed Price + Bidding'),
    ]

    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    UNIT_CHOICES = [
        ('kg', 'Kilogram'),
        ('piece', 'Piece'),
        ('liter', 'Liter'),
        ('dozen', 'Dozen'),
    ]

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products'
    )

    name = models.CharField(max_length=200)

    description = models.TextField()

    category = models.CharField(max_length=100)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default='kg'
    )

    image = models.ImageField(
        upload_to='products/',
        blank=True,
        null=True
    )

    selling_type = models.CharField(
        max_length=20,
        choices=SELLING_TYPE_CHOICES,
        default='fixed'
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )

    is_available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name