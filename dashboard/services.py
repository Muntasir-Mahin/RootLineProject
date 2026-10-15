from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from products.models import Product
from .audit import DecisionError, record_action


@transaction.atomic
def review_product(product_id, *, actor, decision, note=''):
    if decision not in ('verified', 'rejected'):
        raise DecisionError('Choose Verify or Reject.')
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.verification_status != 'pending':
        raise DecisionError('Only products awaiting review can be verified or rejected.')
    product.verification_status = decision
    product.save(update_fields=['verification_status', 'updated_at'])
    record_action(actor=actor, action=f'product.{decision}', target=product,
                  summary=f'{product.get_verification_status_display()} product #{product.pk}: {product.name}'[:255], note=note)
    return product


@transaction.atomic
def review_seller(user_id, *, actor, decision, note=''):
    seller = get_user_model().objects.select_for_update().get(pk=user_id)
    if decision in ('approve', 'reject'):
        if not seller.seller_requested or seller.seller_approved:
            raise DecisionError('This user has no pending seller request.')
        seller.seller_approved = decision == 'approve'
        seller.seller_requested = False
        seller.seller_requested_at = None
    elif decision == 'revoke':
        if not seller.seller_approved:
            raise DecisionError('Only an approved seller can be revoked.')
        seller.seller_approved = False
        seller.seller_requested = False
        seller.seller_requested_at = None
    else:
        raise DecisionError('Choose Approve, Reject or Revoke.')
    seller.save(update_fields=['seller_approved', 'seller_requested', 'seller_requested_at'])
    record_action(actor=actor, action=f'seller.{decision}', target=seller,
                  summary=f'Seller {decision}: {seller.get_username()}', note=note)
    return seller


@transaction.atomic
def request_seller_access(user_id):
    seller = get_user_model().objects.select_for_update().get(pk=user_id)
    if not seller.seller_requested and not seller.seller_approved:
        seller.seller_requested = True
        seller.seller_requested_at = timezone.now()
        seller.save(update_fields=['seller_requested', 'seller_requested_at'])
