from django.core.management.base import BaseCommand, CommandError
from chatbot.ollama import LocalAIError, reply, status


class Command(BaseCommand):
    help = 'Check the local Ollama connection and downloaded model. Optionally send a test question.'

    def add_arguments(self, parser):
        parser.add_argument('--prompt', help='Optional test question; runs local model inference.')

    def handle(self, *args, **options):
        result = status()
        if not result['ready']:
            raise CommandError(result['message'])
        self.stdout.write(self.style.SUCCESS(f"Ready: {result['model']} (local Ollama, no paid API)"))
        if options['prompt']:
            if len(options['prompt']) > 2000:
                raise CommandError('Keep the test question within 2,000 characters.')
            try:
                self.stdout.write(reply(options['prompt'], []))
            except LocalAIError as error:
                raise CommandError(str(error))
