from django.urls import path
from . import views

app_name = 'dashboard'
urlpatterns = [
    path('', views.overview, name='overview'),
    path('payments/', views.payments, name='payments'),
    path('payments/<int:pk>/verify/', views.payment_verify, name='payment_verify'),
    path('payments/<int:pk>/fail/', views.payment_fail, name='payment_fail'),
    path('disputes/', views.disputes, name='disputes'),
    path('disputes/<int:pk>/', views.dispute_detail, name='dispute_detail'),
    path('disputes/<int:pk>/decide/', views.dispute_decide, name='dispute_decide'),
    path('products/', views.products, name='products'),
    path('products/<int:pk>/<str:decision>/', views.product_decide, name='product_decide'),
    path('sellers/', views.sellers, name='sellers'),
    path('sellers/<int:pk>/<str:decision>/', views.seller_decide, name='seller_decide'),
    path('orders/', views.orders, name='orders'),
    path('activity/', views.activity, name='activity'),
]
