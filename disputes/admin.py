from decimal import Decimal

from django.contrib import admin
from django.utils import timezone

from .models import Dispute


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'order',
        'raised_by',
        'reason',
        'status',
        'created_at',
        'resolved_by',
        'resolved_at',
    )

    list_filter = (
        'status',
        'reason',
        'created_at',
    )

    search_fields = (
        'order__id',
        'raised_by__username',
        'order__buyer__username',
        'order__seller__username',
        'description',
    )

    readonly_fields = (
        'order',
        'raised_by',
        'reason',
        'description',
        'seller_response',
        'resolved_by',
        'resolved_at',
        'created_at',
        'updated_at',
    )

    fields = (
        'order',
        'raised_by',

        'reason',
        'description',

        'seller_response',

        'status',
        'admin_note',

        'resolved_by',
        'resolved_at',

        'created_at',
        'updated_at',
    )


    def save_model(self, request, obj, form, change):

        final_statuses = [
            'refund_approved',
            'seller_favored',
            'rejected',
        ]

        # Final decision hole admin + time automatically save
        if obj.status in final_statuses:

            obj.resolved_by = request.user

            if not obj.resolved_at:
                obj.resolved_at = timezone.now()

        else:

            obj.resolved_by = None
            obj.resolved_at = None


        super().save_model(
            request,
            obj,
            form,
            change
        )


        order = obj.order

        payment = getattr(
            order,
            'payment',
            None
        )

        if not payment:
            return


        # ------------------------------------------
        # REFUND APPROVED
        # ------------------------------------------

        if obj.status == 'refund_approved':

            payment.payment_status = 'refunded'
            payment.escrow_status = 'refunded'

            payment.commission_amount = Decimal('0.00')
            payment.seller_amount = Decimal('0.00')

            payment.released_at = None

            payment.save(
                update_fields=[
                    'payment_status',
                    'escrow_status',
                    'commission_amount',
                    'seller_amount',
                    'released_at',
                ]
            )


        # ------------------------------------------
        # SELLER FAVORED / DISPUTE REJECTED
        # ------------------------------------------

        elif obj.status in [
            'seller_favored',
            'rejected',
        ]:

            if (
                payment.payment_status == 'paid'
                and payment.escrow_status == 'held'
            ):

                commission = (
                    payment.amount
                    * Decimal('0.05')
                ).quantize(
                    Decimal('0.01')
                )

                seller_amount = (
                    payment.amount
                    - commission
                )

                payment.commission_amount = commission
                payment.seller_amount = seller_amount

                payment.escrow_status = 'released'
                payment.released_at = timezone.now()

                payment.save(
                    update_fields=[
                        'commission_amount',
                        'seller_amount',
                        'escrow_status',
                        'released_at',
                    ]
                )