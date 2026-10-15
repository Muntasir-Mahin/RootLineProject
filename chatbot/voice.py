"""Local recording transcription with ffmpeg and whisper.cpp, without cloud calls."""
import shutil
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from django.conf import settings

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
BANGLA_CONTEXT = 'বাংলাদেশের বাংলা ভাষায় কথোপকথন।'


class VoiceError(Exception):
    def __init__(self, message, *, status=503):
        super().__init__(message)
        self.status = status


def binary(configured):
    found = shutil.which(str(configured))
    if found:
        return found
    if configured in ('whisper-cli', 'ffmpeg'):
        for prefix in ('/opt/homebrew/bin', '/usr/local/bin'):
            found = shutil.which(str(Path(prefix) / configured))
            if found:
                return found
    raise VoiceError('Voice setup is incomplete. The site owner needs to install whisper.cpp and ffmpeg.')


def configuration():
    if not settings.AI_CHAT_ENABLED:
        raise VoiceError('Ask RootLine is currently switched off.')
    cli, ffmpeg = binary(settings.WHISPER_CLI), binary(settings.FFMPEG_BINARY)
    model = Path(settings.WHISPER_MODEL_PATH).expanduser()
    if not model.is_file() or model.stat().st_size == 0:
        raise VoiceError('Download the multilingual Whisper small model to enable voice questions. See chatbot/README.md.')
    return cli, ffmpeg, model


def status():
    try:
        configuration()
        return {'ready': True, 'message': 'Local voice transcription is set up.'}
    except (VoiceError, OSError) as error:
        return {'ready': False, 'message': str(error) if isinstance(error, VoiceError) else 'The local voice model could not be read.'}


def audio_format(raw):
    # Force an actual audio container; uploaded text/playlists must never cause
    # ffmpeg to open arbitrary URLs or local paths.
    if raw.startswith(b'\x1aE\xdf\xa3'):
        return 'matroska'
    if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        return 'wav'
    if len(raw) >= 12 and raw[4:8] == b'ftyp':
        return 'mov'
    if raw.startswith(b'OggS'):
        return 'ogg'
    raise VoiceError('Choose a WebM, M4A/MP4, WAV or Ogg recording.', status=400)


def validate_transcript(result, language):
    if not result or len(result) > 2000:
        raise VoiceError('No usable speech was found. Try a shorter recording in a quiet place.', status=422)
    if language == 'bn':
        bangla = sum('\u0980' <= char <= '\u09ff' and char.isalpha() for char in result)
        devanagari = sum('\u0900' <= char <= '\u097f' and char.isalpha() for char in result)
        # Script check only: it cannot assess pronunciation, meaning or accuracy.
        # Keep legitimate Bangla/English mixed speech; never translate or
        # transliterate a wrongly recognised Hindi sentence into a guessed question.
        if devanagari > bangla:
            raise VoiceError('বাংলা ঠিকভাবে শনাক্ত হয়নি। আবার পরিষ্কারভাবে পুরো বাক্য বলুন, অথবা প্রশ্নটি লিখুন।', status=422)


def transcribe(upload, language):
    if language not in ('bn', 'en', 'auto'):
        raise VoiceError('Choose Bangla, English or Auto for the recording.', status=400)
    if upload.size > MAX_AUDIO_BYTES:
        raise VoiceError('Keep the recording below 8 MB and 60 seconds.', status=400)
    raw = upload.read(MAX_AUDIO_BYTES + 1)
    if len(raw) > MAX_AUDIO_BYTES:
        raise VoiceError('Keep the recording below 8 MB.', status=400)
    container = audio_format(raw)
    try:
        cli, ffmpeg, model = configuration()
        if language != 'en' and re.search(r'\.en(?:[.-]|$)', model.name, re.IGNORECASE):
            raise VoiceError('Bangla needs the multilingual Whisper model, such as ggml-small.bin, not small.en.')
        with tempfile.TemporaryDirectory(prefix='rootline-voice-') as directory:
            folder = Path(directory)
            source, wav, output = folder / 'recording', folder / 'audio.wav', folder / 'transcript'
            source.write_bytes(raw)
            try:
                subprocess.run([
                    ffmpeg, '-nostdin', '-v', 'error', '-threads', '2',
                    '-protocol_whitelist', 'file,pipe', '-f', container, '-i', str(source),
                    '-vn', '-t', str(MAX_AUDIO_SECONDS + 1), '-ar', '16000', '-ac', '1',
                    '-c:a', 'pcm_s16le', str(wav),
                ], check=True, timeout=20, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                raise VoiceError('This recording could not be read. Record it again or upload a WAV file.', status=400)
            with wave.open(str(wav), 'rb') as audio:
                duration = audio.getnframes() / audio.getframerate()
            if duration < 0.3 or duration > MAX_AUDIO_SECONDS:
                raise VoiceError('Use a recording between 1 and 60 seconds.', status=400)
            command = [
                cli, '-m', str(model), '-f', str(wav), '-l', language,
                '-t', '4', '-otxt', '-of', str(output), '-nt', '-np',
            ]
            if language == 'bn':
                command.extend(['--prompt', BANGLA_CONTEXT])
            subprocess.run(command, check=True, timeout=120, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = output.with_suffix('.txt').read_text(encoding='utf-8').strip()
            validate_transcript(result, language)
            return result
    except VoiceError:
        raise
    except subprocess.TimeoutExpired:
        raise VoiceError('Local transcription took too long. Try a shorter recording.')
    except (subprocess.CalledProcessError, OSError, UnicodeError, wave.Error):
        raise VoiceError('Local voice transcription failed. Check the Whisper model and installation, then try again.')
