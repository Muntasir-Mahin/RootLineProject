from django.urls import path
from . import views

app_name = 'chatbot'
urlpatterns = [
    path('', views.chat, name='chat'),
    path('send/', views.send, name='send'),
    path('clear/', views.clear, name='clear'),
    path('status/', views.connection_status, name='status'),
    path('transcribe/', views.transcribe, name='transcribe'),
]
