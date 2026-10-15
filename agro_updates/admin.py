from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from dashboard.admin import ReadOnlyRecordsAdmin
from .models import Video


@admin.register(Video)
class VideoAdmin(ReadOnlyRecordsAdmin):
    list_display = ('title', 'category', 'language', 'is_published', 'updated_by', 'updated_at')
    list_filter = ('is_published', 'category', 'language')
    search_fields = ('title', 'channel_name')

    def has_add_permission(self, request):
        return True

    def add_view(self, request, form_url='', extra_context=None):
        return redirect('dashboard:agro_video_create')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # Route owner edits through the same validated, audited front-end form.
        if not object_id.isdigit():
            return super().change_view(request, object_id, form_url, extra_context)
        return redirect(reverse('dashboard:agro_video_edit', args=[object_id]))
