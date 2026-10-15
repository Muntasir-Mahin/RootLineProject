from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from .youtube import youtube_video_id


class Video(models.Model):
    CATEGORY_CHOICES = [
        ('news', 'Agro news'), ('crops', 'Crops & soil'), ('livestock', 'Livestock'),
        ('fisheries', 'Fisheries'), ('technology', 'Farming technology'),
    ]
    LANGUAGE_CHOICES = [('bn', 'বাংলা'), ('en', 'English')]

    title = models.CharField(max_length=200)
    youtube_url = models.URLField(max_length=500, verbose_name='YouTube link')
    video_id = models.CharField(max_length=11, unique=True, editable=False)
    summary = models.TextField(max_length=1500, blank=True, help_text='A short explanation of what farmers will learn.')
    channel_name = models.CharField(max_length=150, blank=True, help_text='The original YouTube channel or publisher.')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='news')
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='bn')
    source_published_on = models.DateField(null=True, blank=True, help_text='Original video date, if known.')
    is_published = models.BooleanField(default=False)
    featured = models.BooleanField(default=False, help_text='Highlight this video on the Agro Updates page.')
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name='curated_agro_videos', editable=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name='edited_agro_videos', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-featured', '-published_at', '-pk']
        indexes = [models.Index(fields=['is_published', 'published_at'], name='agro_publication_idx')]

    def clean(self):
        super().clean()
        try:
            self.video_id = youtube_video_id(self.youtube_url)
        except ValidationError as error:
            raise ValidationError({'youtube_url': error.messages})
        self.youtube_url = f'https://www.youtube.com/watch?v={self.video_id}'
        if type(self).objects.filter(video_id=self.video_id).exclude(pk=self.pk).exists():
            raise ValidationError({'youtube_url': 'This YouTube video has already been added. Edit the existing entry instead.'})

    @property
    def thumbnail_url(self):
        return f'https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg'

    @property
    def embed_url(self):
        return f'https://www.youtube-nocookie.com/embed/{self.video_id}'

    def get_absolute_url(self):
        return reverse('agro_updates:detail', args=[self.pk])

    def __str__(self):
        return self.title
