# BERA

One repository, two sides:

- `server/` — API and background jobs (Python, Django REST Framework, Django-Q2 on PostgreSQL)
- `web/` — one Next.js app with three separate areas: website (`/`), company panel (`/company`), admin panel (`/admin`)

The engineering rules and technology decisions are in [CLAUDE.md](CLAUDE.md).

## Run it locally (Windows, PowerShell)

### One-time installs (all free)

1. [Python 3.11+](https://www.python.org/downloads/) — tick "Add python.exe to PATH"
2. [Node.js LTS](https://nodejs.org/)
3. A database, either:
   - **Docker Desktop** (preferred; nothing else to configure), or
   - **PostgreSQL 16** from <https://www.postgresql.org/download/windows/>:
     keep port 5432, remember the `postgres` password, add its `bin` folder to `PATH`,
     and keep it listening on this computer only (the installer default).

### Start everything

```powershell
python scripts/dev.py
```

The first run does the setup by itself: creates `.env` (fake local values) from `.env.example`,
installs Python and web packages, starts the database (Docker if available, otherwise your
native PostgreSQL), applies database changes, and creates a fake admin and fake company.
Running it again is safe and keeps your data.

With native PostgreSQL, the first run stops once and asks you to put the `postgres` password
into `POSTGRES_ADMIN_PASSWORD` in `.env`; run the command again afterwards.

When ready it prints:

| Area          | Address                             |
| ------------- | ----------------------------------- |
| Website       | http://localhost:3000/              |
| Company panel | http://localhost:3000/company       |
| Admin panel   | http://localhost:3000/admin         |
| API health    | http://localhost:8000/api/health/   |

Press `Ctrl+C` to stop everything.

Fake accounts (development only): admin `admin@example.test` / `FAKE-admin-password-dev-only`
and company owner `owner@example.test` / `FAKE-company-password-dev-only`. There are three
separate kinds of account: companies, company users and admin users (see
`server/companies` and `server/adminusers`); they share no table. Passwords are stored only as
Argon2 hashes. A local database from before this change needs `python scripts/dev.py reset-db`.

### Other commands

```powershell
python scripts/dev.py reset-db   # empties the local database (asks first), then re-creates it
python scripts/dev.py test       # runs all tests (server, scripts and web)
```

If a port (3000, 8000, 5432) is busy or a tool is missing, the command says what to do.

## Settings and secrets

Settings come only from environment variables. `APP_ENV` must be `development`, `staging`
or `production`. Locally they are read from `.env`, which is git-ignored; `.env.example`
lists every setting with fake values.

The central list of required settings is `RequiredSetting` entries in `server/config/secrets.py`.
In staging and production the app refuses to start if any entry is missing or a secret is still
a placeholder (such as the fake values in `.env.example`); it names the settings, never their
values. Development only needs `DJANGO_SECRET_KEY`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`,
`JWT_COMPANY_SECRET`, `JWT_ADMIN_SECRET`, `FIELD_ENCRYPTION_KEY` and `FIELD_HASH_KEY` (the token
secrets, and the two field keys, must each be at least 32 characters and different from each
other). The app never holds `MIGRATION_DATABASE_URL` and the migration step never holds
`DATABASE_URL`. Staging and production also need `TRUSTED_PROXY_COUNT`, `ALLOWED_HOSTS` and
`ALLOWED_ORIGINS` (the https addresses of the website, the only sites allowed to use the API from
a browser), and every database address must end with `?sslmode=verify-full` (or `verify-ca`,
`require`) so the connection is encrypted. Staging and production must use different values for every secret.

A ticket that adds a feature with its own key (AI, payments, email, storage) adds the key to
that list, to `.env.example` (fake value) and to this section, in the same change.

Every change is scanned for secrets by `python scripts/scan_secrets.py` (also part of the test
command and of the automatic checks in `.github/workflows/checks.yml`). A fake value on purpose
needs "fake", "example" or "test-only" in its line, or a `nosecret` comment. If a key leaks,
follow [docs/security/if-a-key-leaks.md](docs/security/if-a-key-leaks.md).

`seed_dev_data` and `reset_dev_db` refuse to run outside development.

### Database accounts and protected data

Three database accounts exist, locally too: the app (rows only, cannot change the structure), the
migrator (`migrate`) and backups (read only). `scripts/dev.py` creates them; staging and
production use `python manage.py provision_database_roles`. See
[docs/security/database.md](docs/security/database.md), which also shows how to store a field
encrypted and still find it by a hash. If you have a local database from before this change, run
`python scripts/dev.py reset-db` once (with Docker also `docker compose down -v` first).

## Library checks and updates

`python scripts/check_vulnerabilities.py` checks the server (pip-audit) and web (npm audit)
libraries against the public advisory databases. It runs on every change and every Monday
(`.github/workflows/vulnerabilities.yml`). A high or critical finding in a production library
fails the check; findings in development tools only warn. A risk we accept is written in
`security/accepted-vulnerabilities.toml` with a reason and a review date; once the date passes
the check fails until someone looks again.

Updating routine (weekly, after the Monday check):

1. Read the check's output. Fix serious findings first.
2. Patch and minor updates: `pip install -U <package>` (then update the range in
   `server/requirements.txt`) or `npm update` in `web/`; run all tests (`python scripts/dev.py test`).
3. Major updates (a library's next big version) get their own ticket, since they can break things.
4. If a fix does not exist or cannot be done now, accept the finding in writing with a review
   date no more than about three months ahead, and say who will look at it.
5. Commit lock files with the update so everyone builds from the same versions.

The tests that prove a known-bad library fails the check need internet access. Offline, run
`python -m pytest -m "not network"`.
