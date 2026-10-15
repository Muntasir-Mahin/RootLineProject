from django.conf import settings
from django.db import models


class Conversation(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='ai_conversation')
    # Clearing history advances this version so an in-flight answer cannot restore it.
    revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class Message(models.Model):
    ROLE_CHOICES = [('user', 'You'), ('assistant', 'RootLine AI')]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    content = models.TextField(max_length=8000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
