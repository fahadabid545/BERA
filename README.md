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

Fake accounts (development only): `fake-admin` / `FAKE-admin-password-dev-only` and
`fake-company-owner` / `FAKE-company-password-dev-only`.

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

The app refuses to start, naming what is missing, if `DJANGO_SECRET_KEY` or `DATABASE_URL`
is absent — and in staging and production also `ALLOWED_HOSTS`. The commands
`seed_dev_data` and `reset_dev_db` refuse to run outside development.
