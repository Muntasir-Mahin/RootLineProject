from django.db import IntegrityError, transaction
from django.utils import timezone

from dashboard.audit import DecisionError, record_action
from dashboard.permissions import CATALOGUE, has_role
from .forms import VIDEO_FIELDS
from .models import Video


def require_editor(actor):
    if not has_role(actor, CATALOGUE):
        raise DecisionError('Only Catalogue staff and the owner can manage Agro Updates.')


@transaction.atomic
def save_video(*, actor, data, video_id=None):
    require_editor(actor)
    video = Video.objects.select_for_update().get(pk=video_id) if video_id is not None else Video(created_by=actor)
    creating = video.pk is None
    for field in VIDEO_FIELDS:
        setattr(video, field, data[field])
    if video.is_published and not video.published_at:
        video.published_at = timezone.now()
    video.updated_by = actor
    video.full_clean()
    try:
        with transaction.atomic():
            video.save()
    except IntegrityError:
        raise DecisionError('This video was just added by another editor. Refresh the list and edit that entry.')
    record_action(actor=actor, action='agro_video.create' if creating else 'agro_video.edit', target=video,
                  summary=f'{"Created" if creating else "Updated"} {"published video" if video.is_published else "video draft"}: {video.title}'[:255])
    return video


@transaction.atomic
def set_publication(video_id, *, actor, published):
    require_editor(actor)
    video = Video.objects.select_for_update().get(pk=video_id)
    if video.is_published == published:
        raise DecisionError('This video is already published.' if published else 'This video is already a draft.')
    video.is_published = published
    if published and not video.published_at:
        video.published_at = timezone.now()
    video.updated_by = actor
    video.save(update_fields=['is_published', 'published_at', 'updated_by', 'updated_at'])
    record_action(actor=actor, action='agro_video.publish' if published else 'agro_video.unpublish', target=video,
                  summary=f'{"Published" if published else "Unpublished"} agro video: {video.title}'[:255])
    return video
