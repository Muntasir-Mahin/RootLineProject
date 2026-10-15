# Ask RootLine: local text, photo and voice chat

This version uses **Ollama + Gemma 3:4b** for text/photos and **whisper.cpp + Whisper small** for speech-to-text. All inference stays on the computer running Django. No subscription, API key, paid API or cloud fallback is required. Model downloads, computer resources and any public hosting are separate costs.

The `feat/voice-image-chat` branch includes the staff dashboard, Agro Updates and earlier local chat fixes. The GitHub ZIP contains the complete project, but does **not** include databases, virtual environments or AI model files.

## 1. Update your existing project in PyCharm

If upgrading from `feat/local-ai-chat`, copy the updated **entire `chatbot/` folder**, including its new migration, into your existing project. Keep your existing database and virtual environment. Add the settings below at the end of `rootline/settings.py`, replacing the earlier AI settings block. Add `local_models/` to `.gitignore`.

```python
# os and BASE_DIR are already defined in RootLine settings.
AI_CHAT_ENABLED = os.environ.get('AI_CHAT_ENABLED', 'true').lower() in ('true', '1', 'yes')
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:4b')
OLLAMA_TIMEOUT = 120
WHISPER_MODEL_PATH = os.environ.get('WHISPER_MODEL_PATH', str(BASE_DIR / 'local_models' / 'ggml-small.bin'))
WHISPER_CLI = os.environ.get('WHISPER_CLI', 'whisper-cli')
FFMPEG_BINARY = os.environ.get('FFMPEG_BINARY', 'ffmpeg')
```

If opening the whole ZIP as a new project, these code changes are already included. Select a Python 3.12+ virtual environment and install the project's existing Django/Pillow dependencies. The chat adds no Python package or npm dependency, but voice needs the separate native tools below. Earlier dashboard installation details are in `docs/dashboard-pycharm.md`.

Keep a stable `DJANGO_SECRET_KEY` in your PyCharm environment so sign-ins survive restarts. Do not commit that value. A new database also needs `python manage.py create_dashboard_roles` and an owner account created with `python manage.py createsuperuser`.

## 2. Ollama / Gemma setup on your Mac

Keep the Ollama app open. If Gemma has already downloaded, do not download it again.

Run these in the **normal Terminal shell** (`%` or `$` prompt), not the model chat (`>>>`). Type `/bye` to leave the model chat first.

```sh
ollama pull gemma3:4b
ollama list
```

If the CLI is missing from PATH, use its full macOS application path:

```sh
"/Applications/Ollama.app/Contents/Resources/ollama" pull gemma3:4b
```

In **PyCharm → Run → Edit Configurations → your Django configuration → Environment variables**, set `OLLAMA_MODEL=gemma3:4b` if an older Qwen setting exists there. When starting Django from Terminal instead, run `export OLLAMA_MODEL=gemma3:4b` in that same terminal before starting it. An old environment variable overrides the new default.

Only `gemma3:4b` supports photos in this version. The older local `qwen3:1.7b`, `qwen3:0.6b` and `qwen3:4b` tags remain supported for text-only questions. No remote/cloud model tags are allowed. Gemma and Whisper small are reasonable models to try on an M4 Mac with 16 GB memory, but speed and quality need testing on the actual laptop.

## 3. Install local voice tools on the Mac

In normal Terminal:

```sh
brew install whisper.cpp ffmpeg
```

The current Homebrew formula is **`whisper.cpp`** (formerly `whisper-cpp`). It installs `whisper-cli`, but does not download a model. If Terminal says `brew: command not found`, install Homebrew using its official instructions at https://brew.sh, follow its printed PATH setup, reopen Terminal, then rerun the command above.

Now open **PyCharm's Terminal in the project folder containing `manage.py`**. Download the multilingual Whisper **small** model into that project:

```sh
mkdir -p local_models
curl -fL --retry 3 -o local_models/ggml-small.bin.download "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
```

Wait for curl to finish successfully, then rename the completed download:

```sh
mv local_models/ggml-small.bin.download local_models/ggml-small.bin
```

Use `small`, **not `small.en`**: the `.en` model is English-only. Ollama does not manage the Whisper model. Keep `local_models/` out of GitHub; when using a newly extracted project ZIP, copy your existing model into its `local_models/` folder or configure `WHISPER_MODEL_PATH` to its existing absolute path.

Django checks PATH plus the normal Apple Silicon `/opt/homebrew/bin` and Intel `/usr/local/bin` locations for the tools. If necessary, set `WHISPER_CLI` and `FFMPEG_BINARY` to the absolute paths printed by `which whisper-cli` and `which ffmpeg`.

## 4. Migrate, check and start RootLine

Activate your existing virtual environment in PyCharm's Terminal. From the folder containing `manage.py`:

```sh
python manage.py migrate
python manage.py check_ollama
python manage.py check_voice
python manage.py runserver
```

`check_ollama` checks model installation/connectivity. `check_voice` checks local tool/model file presence. These setup checks do **not** prove that the models produce good answers or transcriptions.

Text/photos still work if voice setup is missing; voice controls explain which setup is missing. If using PyCharm's Run button, configure environment variables there as well, then restart Django. A hard refresh may be needed to load the updated JavaScript and CSS.

## 5. Use it from the website

Sign in with any ordinary RootLine account. Select **Ask RootLine** from the main navigation or **My account**.

- **Text:** type a question and select Send.
- **Photo:** attach one JPG, PNG or WebP photo, optionally add a question, then Send. Photo-only requests receive a default question about visible farming signs. Photos must be under 5 MB / 16 megapixels; the server re-encodes them without original metadata and scales them to at most 1024 pixels on the longest edge.
- **Voice:** select Bangla, English or Auto, then **Record question**. Allow microphone access. Select **Stop recording**, review/edit the resulting text, then select Send. Recording stops after 55 seconds. Nothing is automatically sent to the language model.
- **Existing recording:** select **Upload recording**. WebM, M4A/MP4, WAV and Ogg are supported, up to 8 MB and 60 seconds. MP3 is not accepted in this version.
- **Listen:** select Listen below an answer. This uses only a matching voice marked local by the browser. If no local Bangla/English voice is available, it shows a message instead of sending text to a cloud voice service. Bangla read-aloud availability depends on the device and browser.
- **Clear my history:** deletes your saved chat messages. It does not delete model downloads.

Microphone recording requires JavaScript, browser permission and **localhost or HTTPS**. A phone opening the laptop's plain HTTP LAN address may not permit microphone recording. Recording upload remains available when microphone capture is unsupported. Text, photo sending and clearing history work without JavaScript.

## Test the actual models

For real language-model inference outside saved conversation history:

```sh
python manage.py check_ollama --prompt "Why might tomato leaves turn yellow?"
python manage.py check_ollama --prompt "টমেটো গাছের পাতা হলুদ হওয়ার সম্ভাব্য কারণ কী?"
```

For real speech recognition with a short WAV recording you supply:

```sh
python manage.py check_voice --audio "/absolute/path/to/question.wav" --language bn
```

These optional checks print the actual model output and do not create chat history. Test a clear plant photo through the website for real vision output. Recordings may be misheard, especially regional accents or background noise; review the text before sending. Images alone do not establish a reliable crop diagnosis.

## Privacy, context and errors

- Login is required. Each user's latest 30 messages are private to that account. Chats do not appear in Django staff admin or the staff Activity log. The database operator and backups can still access retained text.
- Photos are sent only to local Ollama for the current question. They are **not retained in chat storage or public media**. A small attachment flag is kept so history can say a photo was used. If discussing it again later, attach it again. Previous image turns explicitly tell the model that their image is no longer available.
- Recordings are processed through temporary files by local ffmpeg and whisper.cpp, then deleted after success or error. The recognized text is initially an editable draft. It becomes stored conversation text only when the user selects Send successfully. Existing reverse proxies/hosting infrastructure may separately log or buffer uploads according to their configuration.
- No account, order or payment data is added to prompts. The assistant has no tools to change marketplace data or access websites.
- At most 6 previous text messages are sent as context. Text is rendered as escaped plain text. No client-selected model endpoint, system prompt or conversation ID is accepted.
- If a model request fails, no partial question/answer pair is saved. Obvious repetitive loops/question echoes are rejected; flagged previous loops are excluded from inference context. This is not an accuracy check and cannot catch every bad answer. Clear poor chat history before retesting.
- Requests stay on HTTP loopback (`127.0.0.1`, `localhost`, `::1`); redirects and remote URLs are rejected. Leave Ollama port 11434 private. No CORS changes or paid cloud fallback are needed.
- `AI_CHAT_ENABLED=false` disables chat and transcription while allowing history clearing. Per-user in-flight guards and database revision checks handle concurrent tabs in this demo; they are not a distributed rate limiter or a high-traffic server design.

## Limitations and verification

This is push-to-talk, with a review step, rather than an always-listening assistant. There is no live weather, price/news retrieval or verified agricultural knowledge base. Use local agricultural officers to confirm crop treatments. Text/photo reasoning, Bangla transcription and local read-aloud quality must be evaluated on the target Mac.

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
mkdir -p work
ROOTLINE_TEST_DB=work/rootline-media-tests.sqlite3 python manage.py test --noinput
```

Automated tests cover authentication, CSRF, uploads, metadata stripping, image request payloads, temporary audio cleanup, process errors/timeouts, private history and concurrency. A real ffmpeg check uses a fake Whisper executable; HTTP/browser fixtures use fake model replies. These tests verify integration and do **not** evaluate real model quality or real Mac speech output. No fake inference fallback exists in the production application.

Official references:

- https://docs.ollama.com/capabilities/vision
- https://ollama.com/library/gemma3
- https://formulae.brew.sh/formula/whisper.cpp
- https://github.com/ggml-org/whisper.cpp
- https://github.com/ggml-org/whisper.cpp/blob/master/models/download-ggml-model.sh
- https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService
