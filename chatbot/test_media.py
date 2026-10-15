"""Upload/privacy/protocol tests. Fake text is not a model quality evaluation."""
import base64
import io
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from . import ollama, voice
from .forms import QuestionForm
from .images import MAX_IMAGE_BYTES
from .models import Message
from .services import store_turn


def photo():
    data = io.BytesIO()
    image = Image.new('RGB', (1200, 600), '#217445')
    exif = Image.Exif()
    exif[270] = 'PRIVATE ORIGINAL METADATA'
    image.save(data, format='JPEG', exif=exif)
    return SimpleUploadedFile('farm.jpg', data.getvalue(), content_type='image/jpeg')


def recording(seconds=1):
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * int(16000 * seconds))
    return SimpleUploadedFile('voice.wav', data.getvalue(), content_type='audio/wav')


class ImageValidationTests(SimpleTestCase):
    def test_photo_is_resized_reencoded_and_metadata_removed(self):
        form = QuestionForm({'message': 'What is visible?'}, {'image': photo()})
        self.assertTrue(form.is_valid(), form.errors)
        output = Image.open(io.BytesIO(form.cleaned_data['image']))
        self.assertEqual(output.format, 'JPEG')
        self.assertEqual(output.size, (1024, 512))
        self.assertFalse(output.getexif())

    def test_image_only_question_has_a_default_prompt(self):
        form = QuestionForm({}, {'image': photo()})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn('farming photo', form.cleaned_data['message'])

    def test_non_images_and_oversized_uploads_are_rejected(self):
        for data in [b'<svg onload="alert(1)"></svg>', b'x' * (MAX_IMAGE_BYTES + 1)]:
            form = QuestionForm({'message': 'Question'}, {'image': SimpleUploadedFile('fake.jpg', data)})
            self.assertFalse(form.is_valid())
            self.assertIn('image', form.errors)

    def test_too_many_pixels_are_rejected_before_full_decode(self):
        with patch('chatbot.images.MAX_IMAGE_PIXELS', 100):
            form = QuestionForm({'message': 'Question'}, {'image': photo()})
            self.assertFalse(form.is_valid())

    @override_settings(OLLAMA_MODEL='gemma3:4b')
    @patch('chatbot.ollama.request_json', return_value={'message': {'content': 'Protocol fixture answer.'}})
    def test_photo_is_sent_as_base64_only_on_latest_user_message(self, request_json):
        raw = b'prepared JPEG bytes'
        ollama.reply('What is visible?', [{'role': 'user', 'content': 'Old photo question', 'has_image': True},
                                         {'role': 'assistant', 'content': 'Old answer'}], image=raw)
        payload = request_json.call_args.kwargs['payload']
        self.assertEqual(payload['model'], 'gemma3:4b')
        self.assertNotIn('think', payload)
        self.assertEqual(base64.b64decode(payload['messages'][-1]['images'][0]), raw)
        self.assertIn('no longer available', payload['messages'][1]['content'])
        self.assertNotIn('images', payload['messages'][1])
        self.assertIn('cannot confirm a crop disease', payload['messages'][0]['content'])

    @override_settings(OLLAMA_MODEL='qwen3:1.7b')
    @patch('chatbot.ollama.request_json')
    def test_text_only_model_cannot_silently_ignore_a_photo(self, request_json):
        with self.assertRaises(ollama.LocalAIError) as error:
            ollama.reply('Question', [], image=b'JPEG')
        self.assertEqual(error.exception.code, 'vision_unsupported')
        request_json.assert_not_called()


class MediaViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('voice-farmer')
        self.client.force_login(self.user)

    @patch('chatbot.ollama.reply', return_value='Protocol fixture image answer.')
    def test_photo_turn_saves_only_text_and_attachment_flag(self, reply):
        response = self.client.post(reverse('chatbot:send'), {'image': photo()}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['messages'][0]['has_image'])
        self.assertTrue(Message.objects.get(role='user').has_image)
        self.assertIn('image', reply.call_args.kwargs)
        self.assertIsInstance(reply.call_args.kwargs['image'], bytes)
        page = self.client.get(reverse('chatbot:chat'))
        self.assertContains(page, 'Photo attached · not retained')
        self.assertNotContains(page, 'PRIVATE ORIGINAL METADATA')
        self.assertNotContains(page, 'data:image')

    @patch('chatbot.ollama.reply')
    def test_invalid_photo_does_not_reach_model_or_save_history(self, reply):
        response = self.client.post(reverse('chatbot:send'), {'message': 'Question', 'image': SimpleUploadedFile('bad.jpg', b'HTML')}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 400)
        reply.assert_not_called()
        self.assertFalse(Message.objects.exists())

    @patch('chatbot.voice.transcribe', return_value='টমেটো গাছের পাতা হলুদ কেন?')
    @patch('chatbot.ollama.reply')
    def test_transcription_is_a_draft_not_an_automatic_question(self, reply, transcribe):
        response = self.client.post(reverse('chatbot:transcribe'), {'audio': recording(), 'language': 'bn'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.json(), {'text': 'টমেটো গাছের পাতা হলুদ কেন?'})
        reply.assert_not_called()
        self.assertFalse(Message.objects.exists())
        self.assertIsNone(cache.get(f'rootline-chat:busy:{self.user.pk}'))

    def test_transcription_is_authenticated_post_only_and_csrf_protected(self):
        url = reverse('chatbot:transcribe')
        self.assertEqual(self.client.get(url).status_code, 405)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.user)
        self.assertEqual(secured.post(url, {'audio': recording(), 'language': 'en'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, HTTP_ACCEPT='application/json').status_code, 401)

    @patch('chatbot.voice.transcribe')
    def test_language_injection_and_missing_audio_are_rejected(self, transcribe):
        for values in [{'language': 'bn'}, {'audio': recording(), 'language': '--model evil'}]:
            response = self.client.post(reverse('chatbot:transcribe'), values, HTTP_ACCEPT='application/json')
            self.assertEqual(response.status_code, 400)
        transcribe.assert_not_called()

    @patch('chatbot.voice.transcribe', side_effect=voice.VoiceError('Local setup missing'))
    def test_transcription_failure_preserves_existing_chat(self, transcribe):
        store_turn(self.user, 0, 'Existing question', 'Existing answer')
        response = self.client.post(reverse('chatbot:transcribe'), {'audio': recording(), 'language': 'en'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Message.objects.count(), 2)
        self.assertIsNone(cache.get(f'rootline-chat:busy:{self.user.pk}'))

    @patch('chatbot.voice.transcribe')
    def test_chat_and_voice_share_the_in_flight_guard(self, transcribe):
        cache.set(f'rootline-chat:busy:{self.user.pk}', 'busy', 30)
        response = self.client.post(reverse('chatbot:transcribe'), {'audio': recording(), 'language': 'en'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 429)
        transcribe.assert_not_called()

    @patch('chatbot.voice.transcribe', return_value='Reviewed draft')
    def test_non_json_transcription_uses_fixed_redirect_and_private_draft(self, transcribe):
        response = self.client.post(reverse('chatbot:transcribe'), {'audio': recording(), 'language': 'en', 'next': 'https://example.com'})
        self.assertRedirects(response, reverse('chatbot:chat'))
        # assertRedirects already consumed the one-use draft during its GET.
        self.assertFalse(Message.objects.exists())


class VoicePipelineTests(SimpleTestCase):
    def fake_run(self, args, **kwargs):
        self.assertTrue(kwargs['check'])
        self.assertNotIn('shell', kwargs)
        if args[0] == 'fixture-ffmpeg':
            Path(args[-1]).write_bytes(recording(self.duration).read())
            self.work_folder = Path(args[-1]).parent
            self.assertIn('-protocol_whitelist', args)
            self.assertEqual(args[args.index('-f') + 1], 'wav')
        else:
            self.assertEqual(args[args.index('-l') + 1], self.language)
            if self.language == 'bn':
                self.assertEqual(args[args.index('--prompt') + 1], voice.BANGLA_CONTEXT)
            else:
                self.assertNotIn('--prompt', args)
            self.assertNotIn('--translate', args)
            self.assertNotIn('-tr', args)
            Path(args[args.index('-of') + 1]).with_suffix('.txt').write_text(self.output, encoding='utf-8')

    def setUp(self):
        self.duration = 1
        self.language = 'bn'
        self.output = 'Local protocol fixture transcript.'
        self.work_folder = None

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('fixture-model')))
    def test_fixed_local_pipeline_returns_text_and_removes_temporary_recordings(self, configuration):
        with patch('chatbot.voice.subprocess.run', side_effect=self.fake_run) as run:
            self.assertEqual(voice.transcribe(recording(), 'bn'), self.output)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(self.work_folder.exists())

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('fixture-model')))
    def test_overlong_and_empty_transcriptions_are_rejected_and_cleaned(self, configuration):
        for duration, output in [(61, 'Text'), (1, ''), (1, 'x' * 2001)]:
            self.duration, self.output = duration, output
            with patch('chatbot.voice.subprocess.run', side_effect=self.fake_run), self.assertRaises(voice.VoiceError):
                voice.transcribe(recording(), 'bn')
            self.assertFalse(self.work_folder.exists())

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('fixture-model')))
    def test_bangla_request_rejects_devanagari_result_and_cleans_audio(self, configuration):
        self.output = 'आमा कि कल बिल्ल'
        with patch('chatbot.voice.subprocess.run', side_effect=self.fake_run), self.assertRaises(voice.VoiceError) as error:
            voice.transcribe(recording(), 'bn')
        self.assertEqual(error.exception.status, 422)
        self.assertIn('বাংলা ঠিকভাবে শনাক্ত হয়নি', str(error.exception))
        self.assertFalse(self.work_folder.exists())

    def test_bangla_and_bangla_english_mixed_transcripts_are_kept_exactly(self):
        for text in ['আমার টমেটো গাছের পাতা হলুদ কেন?', 'আমার tomato গাছের পাতা হলুদ কেন?', 'Tomato']:
            self.assertIsNone(voice.validate_transcript(text, 'bn'))

    def test_auto_and_english_choices_do_not_apply_a_bangla_script_check(self):
        for language in ['auto', 'en']:
            self.assertIsNone(voice.validate_transcript('यह एक परीक्षण है', language))

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('ggml-small.en.bin')))
    @patch('chatbot.voice.subprocess.run')
    def test_english_only_model_cannot_be_used_for_bangla(self, run, configuration):
        with self.assertRaisesMessage(voice.VoiceError, 'multilingual Whisper model'):
            voice.transcribe(recording(), 'bn')
        run.assert_not_called()

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('fixture-model')))
    def test_english_and_auto_language_flags_are_preserved_without_bangla_prompt(self, configuration):
        for language in ['en', 'auto']:
            self.language = language
            with patch('chatbot.voice.subprocess.run', side_effect=self.fake_run):
                self.assertEqual(voice.transcribe(recording(), language), self.output)

    @patch('chatbot.voice.subprocess.run')
    def test_playlists_and_oversized_audio_never_launch_a_process(self, run):
        for data in [b'#EXTM3U\nhttps://example.com/private', b'x' * (voice.MAX_AUDIO_BYTES + 1)]:
            with self.assertRaises(voice.VoiceError):
                voice.transcribe(SimpleUploadedFile('fake.wav', data), 'en')
        run.assert_not_called()

    @override_settings(AI_CHAT_ENABLED=False)
    @patch('chatbot.voice.subprocess.run')
    def test_disabled_chat_cannot_run_voice(self, run):
        with self.assertRaises(voice.VoiceError):
            voice.transcribe(recording(), 'bn')
        run.assert_not_called()

    @patch('chatbot.voice.configuration', return_value=('fixture-whisper', 'fixture-ffmpeg', Path('fixture-model')))
    @patch('chatbot.voice.subprocess.run', side_effect=subprocess.TimeoutExpired('fixture', 20))
    def test_timeout_has_a_clear_error(self, run, configuration):
        with self.assertRaisesMessage(voice.VoiceError, 'took too long'):
            voice.transcribe(recording(), 'bn')

    @patch('chatbot.voice.binary', return_value='/fixture/executable')
    @override_settings(WHISPER_MODEL_PATH='/nonexistent/rootline-model.bin')
    def test_missing_model_is_reported_without_transcription(self, binary):
        self.assertFalse(voice.status()['ready'])

    @patch('chatbot.voice.status', return_value={'ready': False, 'message': 'Download the model'})
    def test_check_voice_command_reports_setup_error(self, status):
        with self.assertRaisesMessage(CommandError, 'Download the model'):
            call_command('check_voice', stdout=io.StringIO())

    def test_real_ffmpeg_decodes_audio_with_a_fake_whisper_executable(self):
        # Actual ffmpeg + subprocess/filesystem integration; NOT actual ASR quality.
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('Install ffmpeg to run the real audio decoding check.')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / 'fixture.bin'
            model.write_bytes(b'fixture only')
            cli = root / 'whisper-fixture'
            cli.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index("-of") + 1]).with_suffix(".txt").write_text("Protocol fixture only.")\n')
            cli.chmod(0o700)
            with override_settings(WHISPER_CLI=str(cli), FFMPEG_BINARY=ffmpeg, WHISPER_MODEL_PATH=str(model)):
                self.assertTrue(voice.status()['ready'])
                self.assertEqual(voice.transcribe(recording(), 'en'), 'Protocol fixture only.')
