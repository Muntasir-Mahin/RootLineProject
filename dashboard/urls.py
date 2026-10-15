from django.urls import path
from . import views
from agro_updates import staff_views as agro

app_name = 'dashboard'
urlpatterns = [
    path('agro-updates/', agro.video_list, name='agro_videos'),
    path('agro-updates/add/', agro.video_edit, name='agro_video_create'),
    path('agro-updates/<int:pk>/edit/', agro.video_edit, name='agro_video_edit'),
    path('agro-updates/<int:pk>/<str:decision>/', agro.video_publication, name='agro_video_publication'),
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
