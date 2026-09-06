from django.urls import path

from .views import (
    create_auction_view,
    edit_auction_view,
    auction_list_view,
    auction_detail_view,
    place_bid_view,
    auction_winner_checkout_view,
)

urlpatterns = [

    path(
        '',
        auction_list_view,
        name='auction_list'
    ),

    path(
        'create/<int:product_id>/',
        create_auction_view,
        name='create_auction'
    ),

    path(
        '<int:auction_id>/',
        auction_detail_view,
        name='auction_detail'
    ),

    path(
        '<int:auction_id>/bid/',
        place_bid_view,
        name='place_bid'
    ),

path(
    'edit/<int:auction_id>/',
    edit_auction_view,
    name='edit_auction'
),

path(
    '<int:auction_id>/winner-checkout/',
    auction_winner_checkout_view,
    name='auction_winner_checkout'
),
]