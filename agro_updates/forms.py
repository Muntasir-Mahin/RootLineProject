from django import forms

from .models import Video

VIDEO_FIELDS = ('title', 'youtube_url', 'summary', 'channel_name', 'category', 'language',
                'source_published_on', 'is_published', 'featured')


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = VIDEO_FIELDS
        labels = {'is_published': 'Publish on Agro Updates'}
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 4}),
            'youtube_url': forms.URLInput(attrs={'placeholder': 'https://www.youtube.com/watch?v=…'}),
            'source_published_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
