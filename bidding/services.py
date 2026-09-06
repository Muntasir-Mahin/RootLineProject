from django.utils import timezone


def finalize_auction(auction):

    # Cancelled auction change korbo na
    if auction.status == 'cancelled':
        return auction

    # Auction ekhono sesh hoy nai
    if timezone.now() < auction.end_time:
        return auction

    # Already ended
    if auction.status == 'ended':
        return auction

    highest_bid = auction.bids.select_related(
        'bidder'
    ).order_by(
        '-amount',
        'created_at'
    ).first()

    auction.status = 'ended'

    if highest_bid:
        auction.winner = highest_bid.bidder
        auction.winning_bid = highest_bid.amount

        auction.save(
            update_fields=[
                'status',
                'winner',
                'winning_bid',
            ]
        )

    else:
        auction.save(
            update_fields=['status']
        )

    return auction