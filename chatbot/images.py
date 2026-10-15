"""Validate and re-encode transient chat photos; never save them to public media."""
import io
import warnings

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
DEFAULT_IMAGE_QUESTION = 'What can you observe in this farming photo? Explain possible causes and ask for any details you need.'


def prepare_image(upload):
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError('Choose a JPG, PNG or WebP photo smaller than 5 MB.')
    raw = upload.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValidationError('Choose a photo smaller than 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValidationError('Use a JPG, PNG or WebP photo.')
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValidationError('This photo is too large. Resize it below 16 megapixels.')
                source.load()
                photo = ImageOps.exif_transpose(source).convert('RGB')
                photo.thumbnail((1024, 1024))
                output = io.BytesIO()
                # A new JPEG omits the original metadata, including EXIF location.
                photo.save(output, format='JPEG', quality=85)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ValidationError('This photo could not be read. Choose a valid JPG, PNG or WebP image.')
