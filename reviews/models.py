from django.db import models
from django.conf import settings
from products.models import Product
from orders.models import Order


class Review(models.Model):

    RATING_CHOICES = (
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    )

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE
    )

    rating = models.IntegerField(
        choices=RATING_CHOICES
    )

    comment = models.TextField()


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return f"{self.product.name} - {self.rating} Star"