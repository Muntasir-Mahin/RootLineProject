from django.urls import path

from .views import (
    raise_dispute_view,
    seller_dispute_response_view,
)


urlpatterns = [

    path(
        'raise/<int:order_id>/',
        raise_dispute_view,
        name='raise_dispute'
    ),

    path(
        '<int:dispute_id>/seller-response/',
        seller_dispute_response_view,
        name='seller_dispute_response'
    ),

]