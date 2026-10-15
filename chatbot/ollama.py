"""Local-only Ollama client. No cloud fallback, API key or third-party SDK."""
import json
import re
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings

ALLOWED_MODELS = ('qwen3:1.7b', 'qwen3:0.6b', 'qwen3:4b')
RESPONSE_LIMIT = 131072
SYSTEM_PROMPT = (
    'You are RootLine AI, a farming learning assistant for Bangladesh. '
    'Answer the latest question directly in 3 to 5 short sentences. '
    'Use earlier messages only when relevant. Explain possible causes before asking a follow-up question. '
    'State uncertainty and suggest a local agricultural officer for crop treatment. '
    'Do not invent pesticide doses or current weather, prices or news. '
    'You cannot access accounts, orders, payments, websites or tools. '
    'Agro Updates has curated farming videos; staff approve seller requests. '
)


class LocalAIError(Exception):
    def __init__(self, message, *, code='unavailable'):
        super().__init__(message)
        self.code = code


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def configuration():
    if not settings.AI_CHAT_ENABLED:
        raise LocalAIError('Ask RootLine is currently switched off.', code='disabled')
    base = settings.OLLAMA_BASE_URL.rstrip('/')
    try:
        url = urlsplit(base)
        if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1')
                or url.username or url.password or url.path or url.query or url.fragment):
            raise ValueError
        _ = url.port
    except ValueError:
        raise LocalAIError('Local AI configuration needs attention from the site owner.', code='configuration')
    model = settings.OLLAMA_MODEL
    if model not in ALLOWED_MODELS:
        raise LocalAIError('Choose a supported local Qwen model in the server settings.', code='configuration')
    return base, model


def request_json(path, *, payload=None, timeout=3):
    base, _ = configuration()
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    request = Request(base + path, data=body, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    # Only the validated loopback endpoint bypasses proxies, keeping local questions local.
    opener = build_opener(ProxyHandler({}), NoRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(RESPONSE_LIMIT + 1)
        if len(raw) > RESPONSE_LIMIT:
            raise LocalAIError('The local model returned too much data. Try a shorter question.', code='bad_response')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except HTTPError as error:
        if error.code == 404:
            raise LocalAIError('The local model is not installed. The site owner needs to download it in Ollama.', code='model_missing')
        raise LocalAIError('Ollama could not answer this question. Please try again.', code='unavailable')
    except (TimeoutError, URLError, OSError):
        raise LocalAIError('Local AI is offline or taking too long. Open Ollama on the computer running RootLine, then try again.', code='offline')
    except (ValueError, UnicodeError):
        raise LocalAIError('The local AI returned an unreadable reply. Please try again.', code='bad_response')


def status():
    try:
        _, model = configuration()
        result = request_json('/api/tags', timeout=3)
        models = result.get('models')
        if not isinstance(models, list):
            raise LocalAIError('The local model list could not be read.', code='bad_response')
        if not any(isinstance(item, dict) and item.get('name') == model for item in models):
            return {'ready': False, 'code': 'model_missing', 'message': f'Download {model} in Ollama to start chatting.'}
        return {'ready': True, 'code': 'ready', 'message': 'Local AI is ready', 'model': model}
    except LocalAIError as error:
        return {'ready': False, 'code': error.code, 'message': str(error)}


def words(text):
    # Keep Bangla vowel marks as well as Latin letters when comparing phrases.
    return re.sub(r'[^\w\s\u0980-\u09ff]', ' ', text.casefold()).split()


def is_repetitive(content):
    """Conservative loop check, not a factual accuracy or general quality check."""
    tokens = words(content)
    if len(tokens) < 24:
        return False
    phrases = Counter(tuple(tokens[i:i + 8]) for i in range(len(tokens) - 7))
    duplicates = sum(count - 1 for count in phrases.values())
    return duplicates / (len(tokens) - 7) >= 0.3


def reply(question, history):
    _, model = configuration()
    context = [{'role': item['role'], 'content': item['content'][:1800]}
               for item in history[-6:] if item['role'] in ('user', 'assistant')]
    # Do not feed a previous generation loop back to the model. Saved history
    # remains intact until its owner chooses to clear it.
    if any(is_repetitive(item['content']) for item in context if item['role'] == 'assistant'):
        context = []
    language = 'Bangla' if re.search(r'[\u0980-\u09ff]', question) else 'English'
    prompt = SYSTEM_PROMPT + f'For this reply, write in {language}. Do not repeat the question or your sentences.'
    result = request_json('/api/chat', timeout=settings.OLLAMA_TIMEOUT, payload={
        'model': model, 'stream': False, 'think': False, 'keep_alive': '5m',
        'messages': [{'role': 'system', 'content': prompt}, *context,
                     {'role': 'user', 'content': question}],
        'options': {'num_predict': 350, 'num_ctx': 4096, 'temperature': 0.3,
                    'repeat_penalty': 1.15, 'repeat_last_n': 256},
    })
    message = result.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LocalAIError('The local model did not return an answer. Try rephrasing your question.', code='bad_response')
    if is_repetitive(content) or (len(words(question)) >= 5 and words(content) == words(question)):
        raise LocalAIError(
            'The local model repeated text instead of answering. Clear my history and try a shorter question. '
            'If this continues, ask the site owner to try a stronger local model.', code='repetitive_response')
    return content.strip()[:8000]
