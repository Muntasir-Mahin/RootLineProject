from django.urls import path
from .views import make_payment_view

urlpatterns = [
    path(
        'pay/<int:order_id>/',
        make_payment_view,
        name='make_payment'
    ),
]