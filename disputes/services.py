from django.db import transaction
from django.utils import timezone

from dashboard.audit import DecisionError, record_action
from payments.services import (
    OPEN_DISPUTE_STATUSES, _refund_locked, _release_locked, lock_order_payment,
)
from .models import Dispute

FINAL_DISPUTE_STATUSES = ('refund_approved', 'seller_favored', 'rejected')
DECISIONS = ('under_review',) + FINAL_DISPUTE_STATUSES


@transaction.atomic
def decide_dispute(dispute_id, *, actor, decision, note=''):
    if decision not in DECISIONS:
        raise DecisionError('Choose a valid dispute decision.')
    order_id = Dispute.objects.values_list('order_id', flat=True).get(pk=dispute_id)
    order, payment = lock_order_payment(order_id)
    dispute = Dispute.objects.select_for_update().get(pk=dispute_id)
    if dispute.resolved_at or dispute.status not in OPEN_DISPUTE_STATUSES:
        raise DecisionError('This dispute has already been resolved. A decision can only be made once.')
    if dispute.status == decision:
        raise DecisionError('This dispute is already under review.')
    if decision == 'refund_approved':
        _refund_locked(order, payment, actor=actor, note=note)
    elif decision in ('seller_favored', 'rejected'):
        _release_locked(order, payment, actor=actor, note=note)
    dispute.status = decision
    dispute.admin_note = note
    if decision in FINAL_DISPUTE_STATUSES:
        dispute.resolved_by = actor
        dispute.resolved_at = timezone.now()
    dispute.save(update_fields=['status', 'admin_note', 'resolved_by', 'resolved_at', 'updated_at'])
    record_action(actor=actor, action=f'dispute.{decision}', target=dispute,
                  summary=f'{dispute.get_status_display()} for order #{order.pk}', note=note)
    return dispute


@transaction.atomic
def raise_dispute(order_id, *, actor, reason, description):
    order, payment = lock_order_payment(order_id)
    if order.buyer_id != actor.pk:
        raise DecisionError('Only the buyer can dispute this order.')
    if (order.status != 'shipped' or payment.payment_status != 'paid' or payment.escrow_status != 'held'):
        raise DecisionError('Only a shipped order with payment held in escrow can be disputed.')
    if Dispute.objects.filter(order=order).exists():
        raise DecisionError('This order already has a dispute.')
    return Dispute.objects.create(order=order, raised_by=actor, reason=reason, description=description)


@transaction.atomic
def respond_to_dispute(dispute_id, *, actor, response):
    order_id = Dispute.objects.values_list('order_id', flat=True).get(pk=dispute_id)
    order, _ = lock_order_payment(order_id)
    dispute = Dispute.objects.select_for_update().get(pk=dispute_id)
    if order.seller_id != actor.pk:
        raise DecisionError('Only the seller can respond to this dispute.')
    if dispute.resolved_at or dispute.status not in OPEN_DISPUTE_STATUSES:
        raise DecisionError('This dispute has already been resolved.')
    dispute.seller_response = response
    if dispute.status == 'open':
        dispute.status = 'seller_responded'
    dispute.save(update_fields=['seller_response', 'status', 'updated_at'])
    return dispute
