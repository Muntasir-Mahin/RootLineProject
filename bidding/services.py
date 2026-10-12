from django.db import transaction
from django.utils import timezone

from products.models import Product
from .models import Auction


@transaction.atomic
def finalize_auction(auction):
    # Match the product -> auction lock order used by bids and checkout.
    Product.objects.select_for_update().get(pk=auction.product_id)
    auction = Auction.objects.select_for_update().get(pk=auction.pk)
    if auction.status == 'cancelled' or auction.order_id:
        return auction
    now = timezone.now()
    if now < auction.end_time:
        if auction.status == 'upcoming' and auction.start_time <= now:
            auction.status = 'active'
            auction.save(update_fields=['status'])
        return auction

    if auction.status == 'ended' and auction.winner_id is not None and auction.winning_bid is not None:
        return auction

    # Repair legacy auctions marked ended before their winner was recorded.
    highest_bid = auction.bids.exclude(bidder_id=auction.product.seller_id).order_by(
        '-amount', 'created_at', 'pk'
    ).first()
    auction.status = 'ended'
    auction.winner_id = highest_bid.bidder_id if highest_bid else None
    auction.winning_bid = highest_bid.amount if highest_bid else None
    auction.save(update_fields=['status', 'winner', 'winning_bid'])
    return auction
