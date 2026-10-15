from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm

from .audit import DecisionError
from .models import AuditRecord


class NoteActionForm(ActionForm):
    note = forms.CharField(required=False, max_length=4000, label='Decision note')


class ServiceActionMixin:
    action_form = NoteActionForm

    def run_service(self, request, queryset, service, **kwargs):
        successful = 0
        for obj in queryset.order_by('pk'):
            try:
                service(obj.pk, actor=request.user, note=request.POST.get('note', ''), **kwargs)
            except DecisionError as error:
                self.message_user(request, f'#{obj.pk}: {error}', level=messages.ERROR)
            else:
                successful += 1
        if successful:
            self.message_user(request, f'{successful} decision(s) saved and audited.', level=messages.SUCCESS)


class ReadOnlyRecordsAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditRecord)
class AuditRecordAdmin(ReadOnlyRecordsAdmin):
    list_display = ('actor_name', 'action', 'target', 'summary', 'timestamp')
    list_filter = ('action',)
    search_fields = ('actor_name', 'summary', 'note', 'target')

    def has_change_permission(self, request, obj=None):
        return False
