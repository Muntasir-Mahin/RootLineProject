from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from dashboard.permissions import CATALOGUE, has_role
from .models import Video


def published_videos():
    return Video.objects.filter(is_published=True, published_at__lte=timezone.now())


@require_GET
def index(request):
    queryset = published_videos()
    counts = dict(queryset.values('category').annotate(total=Count('pk')).values_list('category', 'total'))
    category = request.GET.get('category', '')
    language = request.GET.get('language', '')
    search = request.GET.get('q', '').strip()[:150]
    if category in dict(Video.CATEGORY_CHOICES):
        queryset = queryset.filter(category=category)
    else:
        category = ''
    if language in dict(Video.LANGUAGE_CHOICES):
        queryset = queryset.filter(language=language)
    else:
        language = ''
    if search:
        queryset = queryset.filter(Q(title__icontains=search) | Q(summary__icontains=search) | Q(channel_name__icontains=search))
    return render(request, 'agro_updates/index.html', {
        'page_obj': Paginator(queryset, 9).get_page(request.GET.get('page')),
        'categories': [{'value': key, 'label': label, 'count': counts.get(key, 0)} for key, label in Video.CATEGORY_CHOICES],
        'selected_category': category, 'selected_language': language, 'search': search,
        'languages': Video.LANGUAGE_CHOICES, 'can_manage': has_role(request.user, CATALOGUE),
        'total_videos': sum(counts.values()),
    })


@require_GET
def detail(request, pk):
    video = get_object_or_404(published_videos(), pk=pk)
    related = published_videos().filter(category=video.category).exclude(pk=pk)[:3]
    return render(request, 'agro_updates/detail.html', {'video': video, 'related_videos': related})
