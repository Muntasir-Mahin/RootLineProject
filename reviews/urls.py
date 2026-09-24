from django.urls import path

from .views import (
    add_review_view,
    seller_reviews_view
)


urlpatterns = [

    path(
        'add/<int:product_id>/<int:order_id>/',
        add_review_view,
        name='add_review'
    ),
    path(
    'seller/',
    seller_reviews_view,
    name='seller_reviews'
),

]