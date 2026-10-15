import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}\Z')
YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'}


def youtube_video_id(value):
    """Extract an ID from known YouTube URLs without fetching user-supplied URLs."""
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ('http', 'https') or url.username or url.password or url.port not in (None, 80, 443):
            raise ValueError
        host = (url.hostname or '').lower()
        parts = url.path.strip('/').split('/')
        if host in ('youtu.be', 'www.youtu.be') and len(parts) == 1:
            video_id = parts[0]
        elif host in YOUTUBE_HOSTS and url.path == '/watch':
            values = parse_qs(url.query).get('v', [])
            if len(values) != 1:
                raise ValueError
            video_id = values[0]
        elif host in YOUTUBE_HOSTS and len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
            video_id = parts[1]
        else:
            raise ValueError
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError
        return video_id
    except (ValueError, AttributeError):
        raise ValidationError('Enter a valid YouTube video link, such as https://www.youtube.com/watch?v=VIDEO_ID.')
