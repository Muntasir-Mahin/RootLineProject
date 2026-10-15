# Ask RootLine: local AI demo

This version adds a real chat interface backed by **local Ollama**, with no paid API, API key or cloud fallback. It uses `qwen3:1.7b` by default and can also use `qwen3:0.6b`. Django and Ollama must run on the same computer for the default setup.

The branch `feat/local-ai-chat` includes the earlier staff dashboard and Agro Updates features. Its GitHub ZIP contains the whole updated project.

## Run on your Mac in PyCharm

1. Keep the Ollama application open. If not already downloaded, get the model:

   ```sh
   ollama pull qwen3:1.7b
   ```

2. Update the project files or open the extracted branch ZIP in PyCharm. Select your existing Python 3.12+ virtual environment. The chat needs no new Python or npm dependencies beyond the project's Django/Pillow setup.
3. From the folder containing `manage.py`, with your virtual environment active, run:

   ```sh
   python manage.py migrate
   python manage.py check_ollama
   python manage.py runserver
   ```

4. Sign in to RootLine with an ordinary user, seller, staff or owner account. Select **Ask RootLine** in the main navigation or on **My account**. The route is `/ask-rootline/`.
5. Type a farming question and select **Send**. Recent questions and answers are included as context. The first reply can take longer while the model loads.

If using a new database, also run `python manage.py create_dashboard_roles` and create an owner with `python manage.py createsuperuser` as needed. Keep a stable `DJANGO_SECRET_KEY` in PyCharm/deployment environment variables as documented by the earlier update, so logins survive server restarts.

### Test actual model output

```sh
python manage.py check_ollama --prompt "তুমি কি বাংলায় উত্তর দিতে পারো?"
```

`check_ollama` first checks that the local server is reachable and the configured model is installed. The optional `--prompt` performs real local inference. Neither command needs a subscription or API key.

If `ollama` is not in Terminal's PATH on macOS, open `/Applications/Ollama.app` and allow its CLI setup, or use:

```sh
"/Applications/Ollama.app/Contents/Resources/ollama" pull qwen3:1.7b
```

If Ollama is not already running as an application/service, use `ollama serve` in a separate terminal. Do not start a second server if the app is already running.

## Smaller model

If the laptop is slow or short on memory:

```sh
ollama pull qwen3:0.6b
```

Set `OLLAMA_MODEL=qwen3:0.6b` in PyCharm's Run Configuration environment variables, then restart Django. The smaller model can give weaker answers, especially on detailed agricultural or multilingual questions. No claims of agronomic accuracy are made for either model.

## Settings

| Setting/environment variable | Default | Purpose |
| --- | --- | --- |
| `AI_CHAT_ENABLED` | `true` | Set `false` to disable inference while retaining the ability to clear saved history. |
| `OLLAMA_MODEL` | `qwen3:1.7b` | The two supported local model tags are `qwen3:1.7b` and `qwen3:0.6b`. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Must remain an HTTP loopback address (`127.0.0.1`, `localhost`, `::1`). Remote/cloud URLs are rejected. |
| `OLLAMA_TIMEOUT` (Django setting) | `120` | Local inference timeout in seconds. |

Leave Ollama's network binding at localhost. The browser calls Django; Django calls Ollama. CORS changes and public exposure of port 11434 are unnecessary. To disable Ollama's cloud features globally as well, configure its `OLLAMA_NO_CLOUD=1` environment variable using Ollama's instructions and restart Ollama. RootLine itself already restricts requests to loopback and the two local model tags.

## History and privacy

- Existing RootLine login is required. No ChatGPT account is needed.
- Each user's conversation is scoped to their own account. Clients cannot choose another user's conversation ID or inject system messages.
- The latest **30 messages** are retained in the database. Only the latest **6 prior messages** plus the new question and server prompt are sent to the local model.
- **Clear my history** is a POST action that deletes the user's saved messages. A response already being generated cannot recreate cleared history.
- Failed model calls store no question/answer pair. There is no fake response fallback.
- Chats are not registered in Django admin or written to the staff Activity log. They remain database records, so the database operator can access them and backups may contain older messages.
- Account, order and payment details are not added to model prompts. The model has no tools and cannot change marketplace records.
- User and model text render as plain escaped text, not executable HTML or Markdown HTML.

## Limits of this demo

The local model is not an expert and has no live weather, prices, news, web browsing, YouTube transcripts or verified-document retrieval. The interface explains this. It can ask follow-up questions and respond in Bangla/English, but answer quality should be checked on the target laptop. Local inference has no API fee but uses your computer's resources; public hosting is not included.

The cache prevents a user from sending another question while one is running in a single Django process. Database revision checks protect against conflicting tabs/workers and history clearing. This is not a distributed rate limiter or a high-traffic deployment design. A production deployment would need appropriate authentication, resource limits, distributed coordination and reviewed agricultural sources.

## Validation

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test chatbot
mkdir -p work
ROOTLINE_TEST_DB=work/rootline-chat-tests.sqlite3 python manage.py test --noinput
```

Automated tests mock model text and use a local HTTP protocol fixture for request/error handling. They do not evaluate a downloaded model's answer quality. Run the optional `check_ollama --prompt` command on the laptop for that check.

Official references:

- https://docs.ollama.com/macos
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/faq
- https://ollama.com/library/qwen3
