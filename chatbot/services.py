from uuid import uuid4
from contextlib import contextmanager

from django.core.cache import cache
from django.db import transaction

from . import ollama
from .models import Conversation, Message

HISTORY_LIMIT = 30


class ChatError(Exception):
    def __init__(self, message, *, status=409):
        super().__init__(message)
        self.status = status


def history_for(user):
    return list(Message.objects.filter(conversation__user=user).order_by('pk').values('role', 'content', 'created_at', 'has_image'))


@transaction.atomic
def store_turn(user, revision, question, answer, *, has_image=False):
    conversation, _ = Conversation.objects.get_or_create(user=user)
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    if conversation.revision != revision:
        raise ChatError('Your chat changed in another tab. Refresh the page before sending again.')
    Message.objects.bulk_create([
        Message(conversation=conversation, role='user', content=question, has_image=has_image),
        Message(conversation=conversation, role='assistant', content=answer),
    ])
    conversation.revision += 1
    conversation.save(update_fields=['revision', 'updated_at'])
    keep = list(conversation.messages.order_by('-pk').values_list('pk', flat=True)[:HISTORY_LIMIT])
    conversation.messages.exclude(pk__in=keep).delete()
    return history_for(user)


@contextmanager
def local_task(user):
    # One local-model request per user per process. DB revisions also guard other tabs/workers.
    key, token = f'rootline-chat:busy:{user.pk}', uuid4().hex
    if not cache.add(key, token, timeout=180):
        raise ChatError('Your previous question is still being answered. Please wait.', status=429)
    try:
        yield
    finally:
        if cache.get(key) == token:
            cache.delete(key)


def ask(user, question, *, image=None):
    with local_task(user):
        conversation = Conversation.objects.filter(user=user).first()
        revision = conversation.revision if conversation else 0
        history = history_for(user)
        # Never hold a database transaction open while waiting for the model.
        answer = ollama.reply(question, history, image=image) if image else ollama.reply(question, history)
        return store_turn(user, revision, question, answer, has_image=bool(image))


@transaction.atomic
def clear_history(user):
    conversation, _ = Conversation.objects.get_or_create(user=user)
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    conversation.messages.all().delete()
    conversation.revision += 1
    conversation.save(update_fields=['revision', 'updated_at'])
