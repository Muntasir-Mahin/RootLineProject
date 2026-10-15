# Agro Updates: curated YouTube videos

This update is on `feat/agro-updates`, which includes the earlier staff dashboard. Run `python manage.py migrate` after updating the code. No new Python dependency or YouTube API key is required.

Visitors and farmers can open **Agro Updates** in the marketplace navigation or on **My account**. The page is `/agro-updates/` and shows published videos with thumbnails, summaries, language, category, original channel and a video detail/player page. Search, topic/language filtering and pagination work without JavaScript. The stylesheet is independent of Tailwind.

The owner and **Catalogue** staff manage videos through **Staff dashboard → Agro Updates** (`/dashboard/agro-updates/`). Finance, Support and unassigned staff do not receive editing access. The existing owner-only Django admin's Video entry sends owners to the same front-end forms.

## Add a video

1. Select **Add video**.
2. Paste a normal YouTube watch link, youtu.be share link, Shorts or live-video link.
3. Add an informative title and short summary. Bangla text is supported.
4. Select a topic and language; optionally supply the creator/channel and original video date. These are editorial fields, not fetched automatically from YouTube.
5. Check **Publish on Agro Updates** to make the video visible, or leave it unchecked to save a draft.
6. Check **Featured** to place it ahead of other videos.
7. Save. The thumbnail and video player URLs are generated from the validated video ID.

Use **Unpublish** to hide a video without deleting its history. Drafts are unavailable to visitors, including direct detail URLs. Staff creates, edits, publishes and unpublishes are audited in the Activity log. Publication buttons require POST and CSRF.

Only known YouTube URL formats are accepted. Equivalent links to the same video cannot create duplicate entries. The server never fetches arbitrary submitted URLs. Thumbnails load from YouTube, and playback uses YouTube's privacy-enhanced embed domain. Private, deleted, restricted or non-embeddable videos may not play; a **Watch on YouTube** link remains available. The admin should check availability and content before publication.

The section is a manually curated collection, not a live news feed. Original video date and RootLine publication date are shown separately. This release does not implement AI chat or make AI provider requests.

## Main files

- `agro_updates/models.py`, `forms.py`, `services.py`, `youtube.py`
- `agro_updates/views.py`, `urls.py`, `staff_views.py`, `admin.py`
- `agro_updates/templates/agro_updates/` and `static/agro_updates/agro.css`
- `dashboard/templates/dashboard/agro_videos.html` and `agro_video_form.html`
- `agro_updates/migrations/0001_initial.py` and `tests.py`

## Checks

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test agro_updates
mkdir -p work
ROOTLINE_TEST_DB=work/rootline-all-tests.sqlite3 python manage.py test --noinput
```

## Django secret configuration

The old hardcoded Django secret has been removed from settings. Configure a new `DJANGO_SECRET_KEY` in PyCharm's Run Configuration environment variables and in the deployed server's secret store. Generate a fresh value locally:

```sh
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Keep that value outside source code and do not commit it to GitHub. Restart the server after setting it. Changing the secret requires users to sign in again, but does not change passwords or remove account data. Development with `DEBUG=True` can start without this variable by generating a temporary key; users will be signed out on each server restart in that mode. `DEBUG=False` requires the environment variable.
