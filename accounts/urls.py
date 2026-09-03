from django.urls import path
from .views import (register_view, login_view, profile_view, logout_view, edit_profile_view,change_password_view,become_seller_view,
                    seller_dashboard_view)


urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    path('profile/', profile_view, name='profile'),
    path('profile/edit/', edit_profile_view, name='edit_profile'),
    path('password/change/', change_password_view, name='change_password'),

    path('become-seller/', become_seller_view, name='become_seller'),
    path('seller/dashboard/', seller_dashboard_view, name='seller_dashboard'),
]