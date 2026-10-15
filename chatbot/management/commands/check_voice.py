from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from chatbot import voice


class Command(BaseCommand):
    help = 'Check local Whisper/ffmpeg setup; optionally transcribe a short recording.'

    def add_arguments(self, parser):
        parser.add_argument('--audio', help='Optional local recording to transcribe (never saved in chat history).')
        parser.add_argument('--language', choices=['bn', 'en', 'auto'], default='bn')

    def handle(self, *args, **options):
        result = voice.status()
        if not result['ready']:
            raise CommandError(result['message'])
        self.stdout.write(self.style.SUCCESS(result['message']))
        if options['audio']:
            try:
                with open(options['audio'], 'rb') as recording:
                    self.stdout.write(voice.transcribe(File(recording), options['language']))
            except (voice.VoiceError, OSError) as error:
                raise CommandError(str(error))
