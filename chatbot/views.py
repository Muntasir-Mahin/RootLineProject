from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import ollama
from .forms import QuestionForm
from .services import ChatError, ask, clear_history, history_for


def wants_json(request):
    return 'application/json' in request.headers.get('Accept', '')


def authenticated_json(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({'error': 'Please sign in to use Ask RootLine.'}, status=401)


@never_cache
@login_required
@require_GET
def chat(request):
    return render(request, 'chatbot/chat.html', {'chat_messages': history_for(request.user),
                                               'chat_enabled': settings.AI_CHAT_ENABLED})


@never_cache
@require_GET
def connection_status(request):
    denied = authenticated_json(request)
    if denied is not None:
        return denied
    return JsonResponse(ollama.status())


def failure(request, message, status):
    if wants_json(request):
        response = JsonResponse({'error': message}, status=status)
        if status == 429:
            response['Retry-After'] = '5'
        return response
    messages.error(request, message)
    return redirect('chatbot:chat')


@never_cache
@require_POST
def send(request):
    denied = authenticated_json(request)
    if denied is not None:
        return denied if wants_json(request) else redirect('login')
    form = QuestionForm(request.POST)
    if not form.is_valid():
        return failure(request, form.errors['message'][0], 400)
    try:
        history = ask(request.user, form.cleaned_data['message'])
    except ollama.LocalAIError as error:
        return failure(request, str(error), 503)
    except ChatError as error:
        return failure(request, str(error), error.status)
    if wants_json(request):
        return JsonResponse({'messages': history})
    return redirect('chatbot:chat')


@never_cache
@require_POST
def clear(request):
    denied = authenticated_json(request)
    if denied is not None:
        return denied if wants_json(request) else redirect('login')
    clear_history(request.user)
    if wants_json(request):
        return JsonResponse({'messages': []})
    messages.success(request, 'Your chat history has been cleared.')
    return redirect('chatbot:chat')
