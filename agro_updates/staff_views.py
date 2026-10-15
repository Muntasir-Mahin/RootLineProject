from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from dashboard.audit import DecisionError
from dashboard.permissions import CATALOGUE, staff_role_required
from dashboard.views import page, panel
from .forms import VideoForm
from .models import Video
from .services import save_video, set_publication


@staff_role_required(CATALOGUE)
@require_GET
def video_list(request):
    selected = request.GET.get('tab', 'published')
    if selected not in ('published', 'draft'):
        selected = 'published'
    tabs = [
        {'value': 'published', 'label': 'Published', 'count': Video.objects.filter(is_published=True).count()},
        {'value': 'draft', 'label': 'Drafts', 'count': Video.objects.filter(is_published=False).count()},
    ]
    queryset = Video.objects.filter(is_published=selected == 'published').order_by('-updated_at', '-pk')
    return panel(request, 'agro_videos', 'Agro Updates', 'agro_videos',
                 page_obj=page(request, queryset), tabs=tabs, selected=selected)


@staff_role_required(CATALOGUE)
@require_http_methods(['GET', 'POST'])
def video_edit(request, pk=None):
    video = get_object_or_404(Video, pk=pk) if pk is not None else None
    form = VideoForm(request.POST if request.method == 'POST' else None, instance=video)
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_video(actor=request.user, data=form.cleaned_data, video_id=pk)
        except ValidationError as error:
            if hasattr(error, 'message_dict'):
                for field, errors in error.message_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error(None, error)
        except DecisionError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Video published on Agro Updates.' if saved.is_published else 'Video saved as a draft.')
            return redirect('dashboard:agro_videos')
    return panel(request, 'agro_video_form', 'Edit video' if video else 'Add video', 'agro_videos', form=form, video=video)


@staff_role_required(CATALOGUE)
@require_POST
def video_publication(request, pk, decision):
    get_object_or_404(Video, pk=pk)
    if decision not in ('publish', 'unpublish'):
        raise Http404
    try:
        set_publication(pk, actor=request.user, published=decision == 'publish')
    except DecisionError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, 'Video published.' if decision == 'publish' else 'Video moved to drafts and hidden from visitors.')
    return redirect('dashboard:agro_videos')
