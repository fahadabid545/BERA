"""One command for local development on Windows (also works on macOS/Linux).

    python scripts/dev.py            start database, API, worker and website
    python scripts/dev.py reset-db   empty the local database, then re-create it
    python scripts/dev.py test       run all tests

Needs only Python, Node.js and either Docker or a native PostgreSQL.
"""

import hashlib
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
WEB = ROOT / "web"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = SERVER / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
API_PORT = 8000
WEB_PORT = 3000
MIN_PYTHON = (3, 11)
# On Windows npm is "npm.cmd", which only a full path from which() can launch.
NPM = shutil.which("npm") or "npm"
SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
# Given a fresh random value in a new .env file; the other values stay the fake ones.
RANDOM_SECRETS = (
    "DJANGO_SECRET_KEY",
    "JWT_COMPANY_SECRET",
    "JWT_ADMIN_SECRET",
    "FIELD_ENCRYPTION_KEY",
    "FIELD_HASH_KEY",
)

POSTGRES_INSTALL_STEPS = """PostgreSQL is not available. Pick one:
  A) Install Docker Desktop (free for personal use), start it, then run this again.
  B) Install PostgreSQL 16 for Windows from https://www.postgresql.org/download/windows/
       1. Run the installer. Keep port 5432; remember the 'postgres' password.
       2. Add its 'bin' folder (for example C:\\Program Files\\PostgreSQL\\16\\bin) to your PATH.
       3. Put that password in POSTGRES_ADMIN_PASSWORD in .env, then run this again.
     Keep PostgreSQL listening on this computer only (the installer default)."""


class SetupError(Exception):
    """A problem the developer can fix; shown as plain text, without a stack trace."""


def read_env_file(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def ensure_env_file(env_file=ENV_FILE, example_file=ENV_EXAMPLE):
    """Create .env from the example with fresh random secrets. Never overwrites."""
    if env_file.exists():
        return False
    text = example_file.read_text(encoding="utf-8")
    for name in RANDOM_SECRETS:
        text = re.sub(
            rf"^{name}=.*$",
            f"{name}={secrets.token_urlsafe(48)}",
            text,
            flags=re.MULTILINE,
        )
    env_file.write_text(text, encoding="utf-8")
    return True


def port_in_use(port):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def require_free_port(port, what):
    if port_in_use(port):
        raise SetupError(
            f"Port {port} ({what}) is already in use. Close the program using it "
            "(maybe another copy of this command) and try again."
        )


def require_tools():
    if sys.version_info < MIN_PYTHON:
        raise SetupError(
            "Python 3.11 or newer is required. Install it from https://www.python.org/"
        )
    for tool, url in (("node", "https://nodejs.org/"), ("npm", "https://nodejs.org/")):
        if not shutil.which(tool):
            raise SetupError(f"'{tool}' was not found. Install Node.js (LTS) from {url}")


def digest_of(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()


def run(command, cwd=ROOT, env=None, what="command"):
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode != 0:
        raise SetupError(f"The {what} failed (see the messages above).")


def ensure_python_dependencies():
    if not VENV_PYTHON.exists():
        print("Creating the Python environment...")
        run([sys.executable, "-m", "venv", str(SERVER / ".venv")], what="Python environment setup")
    stamp = SERVER / ".venv" / ".requirements-hash"
    requirements = [SERVER / "requirements.txt", SERVER / "requirements-dev.txt"]
    wanted = digest_of(requirements)
    if not stamp.exists() or stamp.read_text() != wanted:
        print("Installing Python packages...")
        run(
            [str(VENV_PYTHON), "-m", "pip", "install", "-r", str(requirements[1])],
            what="Python package install",
        )
        stamp.write_text(wanted)


def ensure_web_dependencies():
    stamp = WEB / "node_modules" / ".package-hash"
    wanted = digest_of([WEB / "package.json", WEB / "package-lock.json"])
    if not stamp.exists() or stamp.read_text() != wanted:
        print("Installing web packages...")
        run([NPM, "install", "--no-audit", "--no-fund"], cwd=WEB, what="web package install")
        stamp.write_text(wanted)


def docker_ready():
    if not shutil.which("docker"):
        return False
    probe = subprocess.run(["docker", "info"], capture_output=True)
    return probe.returncode == 0


def start_database_with_docker(port):
    running = subprocess.run(
        ["docker", "compose", "ps", "--status", "running", "-q", "db"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not running:
        require_free_port(port, "database")
    print("Starting the PostgreSQL container...")
    run(["docker", "compose", "up", "-d", "--wait", "db"], what="database start")


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def psql(settings, sql, database="postgres"):
    command = [
        "psql", "-h", "127.0.0.1", "-p", settings["POSTGRES_PORT"],
        "-U", settings["POSTGRES_ADMIN_USER"], "-d", database, "-tAc", sql,
    ]  # fmt: skip
    env = {**os.environ, "PGPASSWORD": settings["POSTGRES_ADMIN_PASSWORD"]}
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise SetupError(
            "Could not talk to PostgreSQL. Check that the PostgreSQL service is running and that "
            "POSTGRES_ADMIN_USER / POSTGRES_ADMIN_PASSWORD in .env are correct."
        )
    return result.stdout.strip()


def ensure_native_database(settings):
    """Create the empty database in a normal PostgreSQL install. The three accounts that use
    it are created afterwards by `provision_accounts`, the same way as in a real deployment."""
    if not shutil.which("psql"):
        raise SetupError(POSTGRES_INSTALL_STEPS)
    if not settings.get("POSTGRES_ADMIN_PASSWORD"):
        raise SetupError("Set POSTGRES_ADMIN_PASSWORD in .env (the 'postgres' password you chose).")
    name = settings["POSTGRES_DB"]
    if not SAFE_NAME.match(name):
        raise SetupError("POSTGRES_DB may only use a-z, 0-9 and _.")
    if not port_in_use(int(settings["POSTGRES_PORT"])):
        raise SetupError("PostgreSQL is not running. Start the 'postgresql' Windows service.")
    if not psql(settings, f"SELECT 1 FROM pg_database WHERE datname = {sql_literal(name)}"):
        psql(settings, f'CREATE DATABASE "{name}"')


def admin_database_url(settings):
    """The administrator's address, given only to the command that creates the accounts."""
    user = quote(settings["POSTGRES_ADMIN_USER"], safe="")
    password = quote(settings["POSTGRES_ADMIN_PASSWORD"], safe="")
    port, database = settings["POSTGRES_PORT"], settings["POSTGRES_DB"]
    return f"postgres://{user}:{password}@127.0.0.1:{port}/{database}"  # nosecret: from .env


def provision_accounts(settings):
    manage(
        settings,
        "provision_database_roles",
        extra_environment={"ADMIN_DATABASE_URL": admin_database_url(settings)},
    )


def start_database(settings):
    """Returns True when this script started a Docker container it should stop later."""
    if docker_ready():
        start_database_with_docker(int(settings["POSTGRES_PORT"]))
        return True
    print("Docker is not available; using the native PostgreSQL installation.")
    ensure_native_database(settings)
    return False


def child_environment(settings):
    return {**settings, **os.environ}


def manage(settings, *arguments, extra_environment=None):
    run(
        [str(VENV_PYTHON), "manage.py", *arguments],
        cwd=SERVER,
        env={**child_environment(settings), **(extra_environment or {})},
        what=f"'{arguments[0]}' step",
    )


def prepare(settings):
    """Everything needed before the app can start. Safe to repeat; never wipes data."""
    started_docker = start_database(settings)
    provision_accounts(settings)
    manage(settings, "migrate", "--noinput")
    if settings.get("APP_ENV") == "development":
        manage(settings, "seed_dev_data")
    return started_docker


def setup_everything():
    require_tools()
    created = ensure_env_file()
    if created:
        print("Created .env from .env.example with fake local values.")
    ensure_python_dependencies()
    ensure_web_dependencies()
    return read_env_file(ENV_FILE)


def spawn(command, cwd, settings):
    options = {"cwd": cwd, "env": child_environment(settings)}
    if IS_WINDOWS:
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return subprocess.Popen(command, **options)


def stop(process):
    if process.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        import signal

        os.killpg(process.pid, signal.SIGTERM)


def print_addresses():
    print(
        f"""
Ready. Open:
  Website        http://localhost:{WEB_PORT}/
  Company panel  http://localhost:{WEB_PORT}/company
  Admin panel    http://localhost:{WEB_PORT}/admin
  API health     http://localhost:{API_PORT}/api/health/
Press Ctrl+C to stop everything."""
    )


def start():
    settings = setup_everything()
    require_free_port(API_PORT, "API")
    require_free_port(WEB_PORT, "website")
    started_docker = prepare(settings)
    python = str(VENV_PYTHON)
    api_address = f"127.0.0.1:{API_PORT}"
    processes = [
        spawn([python, "manage.py", "runserver", api_address, "--noreload"], SERVER, settings),
        spawn([python, "manage.py", "qcluster"], SERVER, settings),
        spawn([NPM, "run", "dev"], WEB, settings),
    ]
    try:
        while not (port_in_use(API_PORT) and port_in_use(WEB_PORT)):
            _exit_if_any_stopped(processes)
            time.sleep(1)
        print_addresses()
        while True:
            _exit_if_any_stopped(processes)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        for process in processes:
            stop(process)
        if started_docker:
            subprocess.run(["docker", "compose", "stop", "db"], cwd=ROOT, capture_output=True)


def _exit_if_any_stopped(processes):
    if any(process.poll() is not None for process in processes):
        raise SetupError("One of the programs stopped unexpectedly (see the messages above).")


def reset_database():
    settings = setup_everything()
    if settings.get("APP_ENV") != "development":
        raise SetupError("Resetting only works with APP_ENV=development.")
    if input("This deletes ALL local data. Type 'yes' to continue: ").strip().lower() != "yes":
        print("Cancelled.")
        return
    start_database(settings)
    manage(settings, "reset_dev_db")
    provision_accounts(settings)
    manage(settings, "migrate", "--noinput")
    manage(settings, "seed_dev_data")
    print("Local database reset.")


def run_tests():
    settings = setup_everything()
    start_database(settings)
    provision_accounts(settings)
    failures = []
    server_tests = subprocess.run(
        [str(VENV_PYTHON), "-m", "pytest"], cwd=ROOT, env=child_environment(settings)
    )
    if server_tests.returncode != 0:
        failures.append("server and scripts")
    web_tests = subprocess.run([NPM, "test"], cwd=WEB, env=child_environment(settings))
    if web_tests.returncode != 0:
        failures.append("web")
    if failures:
        raise SetupError(f"Tests failed: {', '.join(failures)}.")
    print("All tests passed.")


COMMANDS = {"start": start, "reset-db": reset_database, "test": run_tests}


def main(arguments):
    command = arguments[0] if arguments else "start"
    if command not in COMMANDS:
        print(f"Unknown command '{command}'. Use: {', '.join(COMMANDS)}")
        return 2
    try:
        COMMANDS[command]()
    except SetupError as error:
        print(f"\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
