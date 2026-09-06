from django.urls import path
from .views import (add_product_view,my_products_view,edit_product_view,
                    delete_product_view,product_detail_view,marketplace_view,
                    marketplace_product_detail_view)


urlpatterns = [
    path('', marketplace_view, name='marketplace'),
    path('add/', add_product_view, name='add_product'),
    path('my-products/', my_products_view, name='my_products'),
    path('edit/<int:product_id>/', edit_product_view, name='edit_product'),
    path('delete/<int:product_id>/', delete_product_view, name='delete_product'),
    path('detail/<int:product_id>/', product_detail_view, name='product_detail'),
path(
    'view/<int:product_id>/',
    marketplace_product_detail_view,
    name='marketplace_product_detail'
),
]