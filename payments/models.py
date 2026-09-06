from django.db import models




class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verification_pending', 'Verification Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    ESCROW_STATUS_CHOICES = [
        ('not_held', 'Not Held'),
        ('held', 'Held in Escrow'),
        ('released', 'Released to Seller'),
        ('refunded', 'Refunded to Buyer'),
    ]

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='payment'
    )

    transaction_id = models.CharField(
        max_length=100,
        blank=True
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )

    escrow_status = models.CharField(
        max_length=20,
        choices=ESCROW_STATUS_CHOICES,
        default='not_held'
    )

    commission_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    seller_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    released_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Payment for Order #{self.order.id}"