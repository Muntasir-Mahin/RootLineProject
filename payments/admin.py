from django.contrib import admin
from django.utils import timezone

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'order',
        'amount',
        'transaction_id',
        'payment_status',
        'escrow_status',
        'created_at',
    )

    list_filter = (
        'payment_status',
        'escrow_status',
    )

    search_fields = (
        'transaction_id',
        'order__buyer__username',
        'order__seller__username',
    )

    # Payment Status + Escrow Status duita-i editable
    readonly_fields = (
        'commission_amount',
        'seller_amount',
        'paid_at',
        'released_at',
    )

    actions = (
        'verify_payment',
        'mark_payment_failed',
    )

    def save_model(self, request, obj, form, change):

        if obj.payment_status == 'paid':
            if not obj.paid_at:
                obj.paid_at = timezone.now()

        elif obj.payment_status in (
            'pending',
            'verification_pending',
            'failed',
        ):
            obj.paid_at = None

        super().save_model(
            request,
            obj,
            form,
            change
        )

    @admin.action(description='Verify selected payments')
    def verify_payment(self, request, queryset):

        for payment in queryset:

            if (
                payment.payment_status == 'verification_pending'
                and payment.transaction_id
                and payment.order.status != 'cancelled'
            ):
                payment.payment_status = 'paid'
                payment.escrow_status = 'held'
                payment.paid_at = timezone.now()

                payment.save(
                    update_fields=[
                        'payment_status',
                        'escrow_status',
                        'paid_at',
                    ]
                )

    @admin.action(description='Mark selected payments as failed')
    def mark_payment_failed(self, request, queryset):

        for payment in queryset:

            if payment.payment_status == 'verification_pending':

                payment.payment_status = 'failed'
                payment.escrow_status = 'not_held'
                payment.paid_at = None

                payment.save(
                    update_fields=[
                        'payment_status',
                        'escrow_status',
                        'paid_at',
                    ]
                )