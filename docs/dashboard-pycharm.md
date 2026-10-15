# Use the staff dashboard in PyCharm

The GitHub branch `feat/staff-dashboard` contains the complete updated RootLine project. GitHub's **Code > Download ZIP** downloads the whole project, including the dashboard. The repository's `main` branch is unchanged.

## Open the complete updated project

1. Download and extract the ZIP for `feat/staff-dashboard`.
2. Open the extracted folder containing `manage.py` in PyCharm.
3. Select an existing virtual environment or create one using Python 3.12 or newer. Django 6 requires Python 3.12+.
4. Use your local database and environment settings in `rootline/settings.py`. If creating a fresh environment, install the existing runtime dependencies:

   ```sh
   python -m pip install "Django==6.0.9" Pillow
   ```

5. In the PyCharm Terminal, from the directory containing `manage.py`, run:

   ```sh
   python manage.py check
   python manage.py migrate
   python manage.py create_dashboard_roles
   python manage.py runserver
   ```

6. If using a new database without an owner account, run `python manage.py createsuperuser` before starting the server.
7. Open `http://127.0.0.1:8000/admin/` as the owner. Mark each staff user **Active** and **Staff status**, keeping **Superuser status** unchecked. Open **Groups**, select Finance, Support or Catalogue, add users under **Members**, and save.
8. Staff sign in at `http://127.0.0.1:8000/login/` and open `http://127.0.0.1:8000/dashboard/`.

The dashboard stylesheet is independent of Tailwind. The existing marketplace's Tailwind build continues to use its own setup.

## Integrate with your existing local project

Commit or back up local changes and the database first. If your project uses this GitHub repository as `origin`, fetch and check out the feature branch:

```sh
git fetch origin
git switch --track origin/feat/staff-dashboard
```

If the branch is already checked out locally, use `git switch feat/staff-dashboard` instead. PyCharm will reload the changed files. Preserve your local environment/database configuration, then run the migration and role commands above.

For manual integration, extract the source ZIP separately and use PyCharm's Compare Files/Compare Directories tools. Copy the new `dashboard/` app, `payments/services.py`, `disputes/services.py`, `rootline/admin_apps.py`, and `rootline/admin_site.py`. Merge the changes in the existing account, order, payment, dispute and product files. Do not replace an entire app directory with only a subset of its files.

In `rootline/settings.py`, add `'dashboard'` and replace `'django.contrib.admin'` with `'rootline.admin_apps.OwnerAdminConfig'` in `INSTALLED_APPS`. Keep your own secret key, database, hosts and unrelated configuration. Keep `AUTH_USER_MODEL = 'accounts.User'`, CSRF/auth/session/messages middleware, app template discovery and staticfiles.

In `rootline/urls.py`, add `path('dashboard/', include('dashboard.urls'))` while keeping `path('admin/', admin.site.urls)` and your marketplace routes.

The account migration adds `seller_requested_at`. If your local accounts migration history differs, merge the model field and generate a migration against your own latest migration instead of overwriting existing migrations. Adapt the bundled backfill for older seller requests as needed.

## Validate

```sh
python manage.py test dashboard
python manage.py test
```

The implementation passed 107 tests, including concurrency tests, on file-backed SQLite. To run those concurrency tests, the existing settings support `ROOTLINE_TEST_DB`.

macOS/Linux:

```sh
mkdir -p work
ROOTLINE_TEST_DB=work/dashboard-tests.sqlite3 python manage.py test --noinput
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force work
$env:ROOTLINE_TEST_DB = 'work/dashboard-tests.sqlite3'
python manage.py test --noinput
Remove-Item Env:ROOTLINE_TEST_DB
```

Use a disposable test database path. No payment-provider API integration is added; refunds and releases record the existing manual bookkeeping workflow. See `dashboard/README.md` for the role matrix, shared services, audit behavior and commission rounding.
