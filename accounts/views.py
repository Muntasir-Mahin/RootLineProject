from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .forms import RegisterForm, ProfileUpdateForm


def home_view(request):

    if request.user.is_authenticated:
        return redirect('profile')

    return redirect('login')

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('profile')

    return render(request, 'accounts/login.html')

@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html')

@login_required
def become_seller_view(request):
    if request.method == 'POST':
        if not request.user.seller_requested and not request.user.seller_approved:
            request.user.seller_requested = True
            request.user.save(update_fields=['seller_requested'])

        return redirect('profile')

    return redirect('profile')

@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def logout_view(request):
    if request.method == 'POST':
        if request.POST.get('confirm') != 'yes':
            return redirect('logout')
        if request.POST.get('user_id') != str(request.user.pk):
            messages.info(request, 'Your signed-in account changed. Please confirm logout again.')
            return redirect('logout')
        logout(request)
        return redirect('login')

    return render(request, 'accounts/logout.html')


@never_cache
@require_GET
def logout_token_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'signedOut': True})
    return JsonResponse({'csrfToken': get_token(request), 'userId': request.user.pk})


@login_required
def edit_profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {'form': form})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)

        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'accounts/change_password.html', {'form': form})

@login_required
def seller_dashboard_view(request):
    if not request.user.seller_approved:
        return redirect('profile')

    return render(request, 'accounts/seller_dashboard.html')