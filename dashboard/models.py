from django.conf import settings
from django.db import models


class AuditRecord(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=50)
    # Stable identifiers and a snapshot survive deletion of the target or actor.
    target = models.CharField(max_length=200)
    summary = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-pk']

    def __str__(self):
        return self.summary
