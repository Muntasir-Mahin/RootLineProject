from django.contrib import admin
from django.utils import timezone

from .models import Payment


@admin.action(description='Verify payment and hold in escrow')
def verify_payment(modeladmin, request, queryset):

    verified_count = 0

    for payment in queryset.select_related('order'):

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

            verified_count += 1

    modeladmin.message_user(
        request,
        f'{verified_count} payment(s) verified.'
    )


@admin.action(description='Mark payment as failed')
def mark_payment_failed(modeladmin, request, queryset):

    failed_count = 0

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

            failed_count += 1

    modeladmin.message_user(
        request,
        f'{failed_count} payment(s) marked as failed.'
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
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
        'order__id',
        'order__buyer__username',
        'transaction_id',
    )

    readonly_fields = (
        'payment_status',
        'escrow_status',
        'commission_amount',
        'seller_amount',
        'paid_at',
        'released_at',
    )

    actions = [
        verify_payment,
        mark_payment_failed,
    ]