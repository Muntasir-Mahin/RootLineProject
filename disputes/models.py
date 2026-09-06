from django.conf import settings
from django.db import models


class Dispute(models.Model):

    REASON_CHOICES = [
        ('damaged', 'Damaged Product'),
        ('wrong_product', 'Wrong Product'),
        ('quantity_issue', 'Quantity Issue'),
        ('quality_issue', 'Quality Issue'),
        ('not_received', 'Product Not Received'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('seller_responded', 'Seller Responded'),
        ('under_review', 'Under Admin Review'),
        ('refund_approved', 'Refund Approved'),
        ('seller_favored', 'Resolved in Seller Favor'),
        ('rejected', 'Rejected'),
    ]

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='dispute'
    )

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='raised_disputes'
    )

    reason = models.CharField(
        max_length=30,
        choices=REASON_CHOICES
    )

    description = models.TextField()

    seller_response = models.TextField(
        blank=True
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='open'
    )

    admin_note = models.TextField(
        blank=True
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_disputes'
    )

    resolved_at = models.DateTimeField(
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
        return f"Dispute #{self.id} - Order #{self.order.id}"