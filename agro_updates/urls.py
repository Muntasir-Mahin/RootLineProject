from django.urls import path
from . import views

app_name = 'agro_updates'
urlpatterns = [path('', views.index, name='index'), path('<int:pk>/', views.detail, name='detail')]
