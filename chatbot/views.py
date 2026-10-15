from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import ollama, voice
from .forms import QuestionForm, VoiceForm
from .services import ChatError, ask, clear_history, history_for, local_task


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
                                               'chat_enabled': settings.AI_CHAT_ENABLED,
                                               'supports_images': settings.OLLAMA_MODEL in ollama.VISION_MODELS,
                                               'voice_draft': request.session.pop('chat_voice_draft', '')})


@never_cache
@require_GET
def connection_status(request):
    denied = authenticated_json(request)
    if denied is not None:
        return denied
    result = ollama.status()
    result['voice'] = voice.status()
    return JsonResponse(result)


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
    form = QuestionForm(request.POST, request.FILES)
    if not form.is_valid():
        return failure(request, next(iter(form.errors.values()))[0], 400)
    try:
        history = ask(request.user, form.cleaned_data['message'], image=form.cleaned_data['image'])
    except ollama.LocalAIError as error:
        return failure(request, str(error), 503)
    except ChatError as error:
        return failure(request, str(error), error.status)
    if wants_json(request):
        return JsonResponse({'messages': history})
    return redirect('chatbot:chat')


@never_cache
@require_POST
def transcribe(request):
    denied = authenticated_json(request)
    if denied is not None:
        return denied if wants_json(request) else redirect('login')
    form = VoiceForm(request.POST, request.FILES)
    if not form.is_valid():
        return failure(request, next(iter(form.errors.values()))[0], 400)
    try:
        with local_task(request.user):
            text = voice.transcribe(form.cleaned_data['audio'], form.cleaned_data['language'])
    except voice.VoiceError as error:
        return failure(request, str(error), error.status)
    except ChatError as error:
        return failure(request, str(error), error.status)
    if wants_json(request):
        return JsonResponse({'text': text})
    request.session['chat_voice_draft'] = text
    messages.success(request, 'Your recording was transcribed. Review the text before sending.')
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
