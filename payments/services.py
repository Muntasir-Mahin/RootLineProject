"""The single entry point for payment/escrow transitions.

Lock order everywhere: Order -> Payment -> Dispute. Audit writes share the
transaction, so a failed decision cannot leave a partial payment or audit trail.
These services record manual bookkeeping; they do not call a bKash/Nagad API.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from dashboard.audit import DecisionError, record_action
from orders.models import Order
from .models import Payment

COMMISSION_RATE = Decimal('0.05')
OPEN_DISPUTE_STATUSES = ('open', 'seller_responded', 'under_review')


def lock_order_payment(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    try:
        payment = Payment.objects.select_for_update().get(order_id=order_id)
    except Payment.DoesNotExist:
        raise DecisionError('This order has no payment record.')
    return order, payment


def _lock_payment(payment_id):
    order_id = Payment.objects.values_list('order_id', flat=True).get(pk=payment_id)
    return lock_order_payment(order_id)


def _require_held(order, payment):
    if order.status in ('cancelled', 'delivered'):
        raise DecisionError('This order has already been completed or cancelled.')
    if payment.payment_status != 'paid' or payment.escrow_status != 'held':
        raise DecisionError('Only a paid payment held in escrow can be refunded or released.')


def _require_no_dispute(order):
    from disputes.models import Dispute
    if Dispute.objects.filter(order=order, status__in=OPEN_DISPUTE_STATUSES).exists():
        raise DecisionError('Escrow cannot be changed while a dispute is open. Support must decide it first.')


@transaction.atomic
def verify_payment(payment_id, *, actor, note=''):
    order, payment = _lock_payment(payment_id)
    if (payment.payment_status != 'verification_pending' or payment.escrow_status != 'not_held'):
        raise DecisionError('Only payments awaiting verification can be verified.')
    if not payment.transaction_id.strip():
        raise DecisionError('A transaction ID is required before verification.')
    if order.status in ('cancelled', 'delivered'):
        raise DecisionError('Payments for cancelled or completed orders cannot be verified.')
    if payment.amount <= 0 or payment.amount != order.total_amount:
        raise DecisionError('The payment amount must be positive and match the order total.')
    payment.payment_status = 'paid'
    payment.escrow_status = 'held'
    payment.paid_at = timezone.now()
    payment.save(update_fields=['payment_status', 'escrow_status', 'paid_at', 'updated_at'])
    record_action(actor=actor, action='payment.verify', target=payment,
                  summary=f'Verified payment for order #{order.pk}', note=note)
    return payment


@transaction.atomic
def fail_payment(payment_id, *, actor, note=''):
    order, payment = _lock_payment(payment_id)
    if payment.payment_status != 'verification_pending' or payment.escrow_status != 'not_held':
        raise DecisionError('Only payments awaiting verification can be failed.')
    payment.payment_status = 'failed'
    payment.paid_at = None
    payment.save(update_fields=['payment_status', 'paid_at', 'updated_at'])
    record_action(actor=actor, action='payment.fail', target=payment,
                  summary=f'Failed payment for order #{order.pk}', note=note)
    return payment


def _refund_locked(order, payment, *, actor, note):
    _require_held(order, payment)
    payment.payment_status = 'refunded'
    payment.escrow_status = 'refunded'
    payment.commission_amount = Decimal('0.00')
    payment.seller_amount = Decimal('0.00')
    payment.released_at = None
    payment.save(update_fields=['payment_status', 'escrow_status', 'commission_amount',
                                'seller_amount', 'released_at', 'updated_at'])
    order.status = 'cancelled'
    order.save(update_fields=['status', 'updated_at'])
    record_action(actor=actor, action='payment.refund', target=payment,
                  summary=f'Refunded payment and cancelled order #{order.pk}', note=note)
    return payment


def _release_locked(order, payment, *, actor, note):
    _require_held(order, payment)
    payment.commission_amount = (payment.amount * COMMISSION_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    payment.seller_amount = payment.amount - payment.commission_amount
    payment.escrow_status = 'released'
    payment.released_at = timezone.now()
    payment.save(update_fields=['commission_amount', 'seller_amount', 'escrow_status', 'released_at', 'updated_at'])
    order.status = 'delivered'
    order.save(update_fields=['status', 'updated_at'])
    record_action(actor=actor, action='payment.release', target=payment,
                  summary=f'Released escrow for order #{order.pk}; commission BDT {payment.commission_amount}', note=note)
    return payment


@transaction.atomic
def refund_payment(payment_id, *, actor, note=''):
    order, payment = _lock_payment(payment_id)
    _require_no_dispute(order)
    return _refund_locked(order, payment, actor=actor, note=note)


@transaction.atomic
def confirm_delivery(order_id, *, actor):
    order, payment = lock_order_payment(order_id)
    if order.buyer_id != actor.pk:
        raise DecisionError('Only the buyer can confirm delivery.')
    if order.status != 'shipped':
        raise DecisionError('Only a shipped order can be confirmed as delivered.')
    _require_no_dispute(order)
    return _release_locked(order, payment, actor=actor, note='Buyer confirmed delivery.')


@transaction.atomic
def submit_transaction(order_id, *, actor, transaction_id):
    order, payment = lock_order_payment(order_id)
    if order.buyer_id != actor.pk:
        raise DecisionError('Only the buyer can submit this payment.')
    if order.status in ('cancelled', 'delivered') or payment.payment_status not in ('pending', 'failed'):
        raise DecisionError('This payment can no longer be submitted.')
    if payment.escrow_status != 'not_held':
        raise DecisionError('This payment already has an escrow decision.')
    if not transaction_id.strip() or len(transaction_id) > 100:
        raise DecisionError('Enter a valid transaction ID (up to 100 characters).')
    payment.transaction_id = transaction_id.strip()
    payment.payment_status = 'verification_pending'
    payment.save(update_fields=['transaction_id', 'payment_status', 'updated_at'])
    return payment
