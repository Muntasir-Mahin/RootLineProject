"""Local-only Ollama client. No cloud fallback, API key or third-party SDK."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings

ALLOWED_MODELS = ('qwen3:1.7b', 'qwen3:0.6b')
RESPONSE_LIMIT = 131072
SYSTEM_PROMPT = (
    'You are RootLine AI, a general farming learning assistant for Bangladesh. '
    'Answer in the same language as the latest question: Bangla or English. '
    'Use simple, short explanations. Ask about crop, location, season or symptoms when needed. '
    'You are a small local AI model, not a verified agricultural expert. '
    'Do not invent live news, prices, weather, citations, or pesticide doses. '
    'When unsure, say so and suggest checking with a local agricultural officer. '
    'You have no access to accounts, payments, orders, websites or tools and cannot change marketplace data. '
    'For platform help: Agro Updates contains curated farming videos; staff approve seller requests. '
    'Never claim to have checked current data or performed an action.'
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


def reply(question, history):
    _, model = configuration()
    context = [{'role': item['role'], 'content': item['content'][:1800]}
               for item in history[-6:] if item['role'] in ('user', 'assistant')]
    result = request_json('/api/chat', timeout=settings.OLLAMA_TIMEOUT, payload={
        'model': model, 'stream': False, 'think': False, 'keep_alive': '5m',
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, *context,
                     {'role': 'user', 'content': question}],
        'options': {'num_predict': 350, 'num_ctx': 4096, 'temperature': 0.4},
    })
    message = result.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LocalAIError('The local model did not return an answer. Try rephrasing your question.', code='bad_response')
    return content.strip()[:8000]
