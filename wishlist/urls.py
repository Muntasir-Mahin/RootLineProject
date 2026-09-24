from django.urls import path
from .views import (
    add_wishlist,
    remove_wishlist,
    my_wishlist
)


urlpatterns = [

    path(
        'add/<int:product_id>/',
        add_wishlist,
        name='add_wishlist'
    ),


    path(
        'remove/<int:product_id>/',
        remove_wishlist,
        name='remove_wishlist'
    ),


    path(
        '',
        my_wishlist,
        name='my_wishlist'
    ),

]