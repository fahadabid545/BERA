"""Deploys Bera to a Linux server and rolls back, for staging and production side by side.

    python deploy/bera_deploy.py deploy production --ref v1.2.0 --dry-run
    python deploy/bera_deploy.py deploy staging
    python deploy/bera_deploy.py rollback production
    python deploy/bera_deploy.py units production --out /tmp/units

Layout (one folder per environment, nothing shared):

    <root>/<env>/releases/<id>/   the code of one release (kept: the last 5)
    <root>/<env>/current          link to the live release (switched in one step)
    <root>/<env>/previous         link to the release before it (what a rollback returns to)
    <root>/backups/production/    database dumps taken before each production deploy
    <env_dir>/<env>.env           the secrets, outside every release, mode 600

A rollback does NOT undo database changes. Every migration must therefore work with both the
old and the new release: add first, remove only in a later release.
"""

import argparse
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_environments import read_env_file  # noqa: E402

sys.path.insert(0, str(SCRIPTS.parent / "server"))
from config.separation import compare  # noqa: E402

ENVIRONMENTS = ("staging", "production")
SERVICES = ("api", "worker", "web")
KEEP_RELEASES = 5
SERVICE_USER = "bera"
MIGRATION_REMINDER = (
    "REMINDER: a rollback does not undo database changes. Every migration must work with both "
    "the old and the new release (add first, remove only in a later release)."
)

# The numbers for one small server holding both environments and the database. Written once
# here; the service files and the README follow them.
RESOURCES = {
    "production": {
        "api_workers": 2,
        "api_memory": "700M",
        "queue_workers": 2,
        "queue_memory": "600M",
        "web_memory": "350M",
        "web_heap_mb": 256,
        "job_memory": "300M",
    },
    "staging": {
        "api_workers": 1,
        "api_memory": "350M",
        "queue_workers": 1,
        "queue_memory": "350M",
        "web_memory": "250M",
        "web_heap_mb": 160,
    },
}
# Production only (staging holds fake data): backup jobs run by timers, each a short-lived process
# that stops by itself. (name, manage.py command, when, longest it may run)
BACKUP_JOBS = (
    ("backup", "backup_database", "*-*-* 02:30:00 UTC", "2h"),
    ("restore-test", "verify_backup_restore", "Sun *-*-* 04:30:00 UTC", "2h"),
    ("backup-check", "check_backup_fresh", "*-*-* *:15:00 UTC", "10min"),
)
HEALTH_ATTEMPTS = 20
HEALTH_DELAY_SECONDS = 3


class DeployError(Exception):
    """Something stopped the deployment; the message never holds a secret value."""


@dataclass
class Layout:
    root: Path
    env: str
    env_dir: Path

    @property
    def base(self):
        return self.root / self.env

    @property
    def releases(self):
        return self.base / "releases"

    @property
    def current(self):
        return self.base / "current"

    @property
    def previous(self):
        return self.base / "previous"

    @property
    def env_file(self):
        return self.env_dir / f"{self.env}.env"

    @property
    def backups(self):
        return self.root / "backups" / self.env


def link_or_copy(source, target):
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


class Shell:
    """Runs real commands. Tests replace it; dry-run never reaches it."""

    def run(self, argv, *, env=None, cwd=None):
        subprocess.run(argv, check=True, env=env, cwd=cwd)

    def spawn(self, argv, *, env, cwd, log, pidfile):
        with open(log, "ab") as output:
            process = subprocess.Popen(
                argv, env=env, cwd=cwd, stdout=output, stderr=output, start_new_session=True
            )
        Path(pidfile).write_text(str(process.pid))


def http_health(url, host, *, attempts, delay, sleep=time.sleep):
    """True once the address answers 200. The header says the request came over https, as the
    proxy in front would, because the app redirects plain http."""
    request = urllib.request.Request(
        url, headers={"Host": host, "X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1"}
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=5) as reply:
                if reply.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        if attempt + 1 < attempts:
            sleep(delay)
    return False


def database_environment(url):
    """PG* variables for one database address, so no password ever appears in a command line."""
    parts = urlsplit(url)
    return {
        "PGHOST": parts.hostname or "",
        "PGPORT": str(parts.port or 5432),
        "PGUSER": unquote(parts.username or ""),
        "PGPASSWORD": unquote(parts.password or ""),
        "PGDATABASE": parts.path.lstrip("/"),
        "PGSSLMODE": "prefer",
    }


def unit_header(layout, restart_lines):
    """What every service has in common: not root, secrets from the env file outside the releases,
    limited rights."""
    return f"""[Unit]
After=network.target

[Service]
User={SERVICE_USER}
Group={SERVICE_USER}
EnvironmentFile={layout.env_file}
{restart_lines}NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={layout.base}/data
"""


def render_units(env, layout):
    """The systemd service files for one environment: not root, memory limited, the secrets read
    from the env file outside the releases, the code reached through the `current` link."""
    numbers = RESOURCES[env]
    current = layout.current
    common = unit_header(layout, "Restart=on-failure\nRestartSec=5\n")
    api_start = (
        f"{current}/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:${{API_PORT}} "
        f"--workers {numbers['api_workers']} --timeout 60"
    )
    web_start = (
        "/usr/bin/node node_modules/next/dist/bin/next start --port ${WEB_PORT} "
        "--hostname 127.0.0.1"
    )
    units = {
        "api": f"""{common}WorkingDirectory={current}/server
ExecStart={api_start}
MemoryMax={numbers["api_memory"]}

[Install]
WantedBy=multi-user.target
""",
        "worker": f"""{common}WorkingDirectory={current}/server
Environment=Q_CLUSTER_WORKERS={numbers["queue_workers"]}
ExecStart={current}/.venv/bin/python manage.py qcluster
MemoryMax={numbers["queue_memory"]}

[Install]
WantedBy=multi-user.target
""",
        "web": f"""{common}WorkingDirectory={current}/web
Environment=NODE_OPTIONS=--max-old-space-size={numbers["web_heap_mb"]}
ExecStart={web_start}
MemoryMax={numbers["web_memory"]}

[Install]
WantedBy=multi-user.target
""",
    }
    files = {f"bera-{env}-{name}.service": text for name, text in units.items()}
    if env == "production":
        files.update(render_backup_units(layout, numbers["job_memory"]))
    return files


def render_backup_units(layout, memory):
    """A service and a timer for each backup job. `Persistent` runs a job missed while the
    server was off as soon as it is back."""
    files = {}
    for name, command, schedule, longest in BACKUP_JOBS:
        header = unit_header(layout, "Type=oneshot\n")
        files[f"bera-production-{name}.service"] = (
            f"{header}WorkingDirectory={layout.current}/server\n"
            f"ExecStart={layout.current}/.venv/bin/python manage.py {command}\n"
            f"MemoryMax={memory}\nTimeoutStartSec={longest}\n"
        )
        files[f"bera-production-{name}.timer"] = (
            f"[Unit]\nDescription=Bera production {name}\n\n"
            f"[Timer]\nOnCalendar={schedule}\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
    return files


class Deployer:
    def __init__(
        self,
        layout,
        *,
        shell=None,
        out=print,
        dry_run=False,
        simulation=False,
        health=http_health,
        source=None,
        service_user=SERVICE_USER,
        systemctl=("sudo", "systemctl"),
        owner_of=lambda path: path.owner(),
        clock=lambda: datetime.now(UTC),
    ):
        self.layout = layout
        self.shell = shell or Shell()
        self.out = out
        self.dry_run = dry_run
        self.simulation = simulation
        self.health = health
        self.source = Path(source or Path(__file__).resolve().parent.parent)
        self.service_user = service_user
        self.systemctl = list(systemctl)
        self.owner_of = owner_of
        self.clock = clock

    # ----- small helpers
    def say(self, text):
        self.out(("[dry-run] would: " if self.dry_run else "") + text)

    def do(self, text, action):
        """Describes one step, and runs it unless this is a dry run."""
        self.say(text)
        if not self.dry_run:
            return action()
        return None

    def values(self):
        return read_env_file(self.layout.env_file)

    def other_env_file(self):
        other = "production" if self.layout.env == "staging" else "staging"
        return self.layout.env_dir / f"{other}.env"

    def command_environment(self, extra=None):
        return {**os.environ, **self.values(), "APP_ENV": self.layout.env, **(extra or {})}

    # ----- checks before anything changes
    def preflight(self):
        env_file = self.layout.env_file
        if not env_file.is_file():
            raise DeployError(f"The environment file {env_file} does not exist.")
        mode = stat.S_IMODE(env_file.stat().st_mode)
        if mode & 0o077:
            raise DeployError(
                f"{env_file} must be readable only by its owner (mode 600); it is {oct(mode)}."
            )
        if self.service_user == "root":
            raise DeployError("The services must not run as root.")
        if not self.simulation and self.owner_of(env_file) != self.service_user:
            raise DeployError(f"{env_file} must belong to the service user {self.service_user}.")
        values = self.values()
        if values.get("APP_ENV") != self.layout.env:
            raise DeployError(f"APP_ENV in {env_file} must be {self.layout.env}.")
        other = self.other_env_file()
        if other.is_file():
            problems = compare(
                *(
                    (values, read_env_file(other))
                    if self.layout.env == "staging"
                    else (read_env_file(other), values)
                )
            )
            if problems:
                raise DeployError("Staging and production share settings: " + " ".join(problems))
        self.out("Checked the environment file and that staging and production share nothing.")

    # ----- releases
    def release_ids(self):
        if not self.layout.releases.is_dir():
            return []
        return sorted(item.name for item in self.layout.releases.iterdir() if item.is_dir())

    def target_of(self, link):
        return Path(os.readlink(link)).name if link.is_symlink() else None

    def new_release_id(self, ref):
        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{ref.replace('/', '-')[:12]}"

    def switch(self, link, release_id):
        """Points a link at a release in one step (never a moment with no link)."""
        temporary = Path(str(link) + ".new")
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()
        os.symlink(self.layout.releases / release_id, temporary)
        os.replace(temporary, link)

    # ----- the steps of a deploy
    def build_release(self, ref, release_id):
        folder = self.layout.releases / release_id
        archive = Path(str(folder) + ".tar")

        def unpack():
            folder.mkdir(parents=True)
            self.shell.run(
                ["git", "-C", str(self.source), "archive", "--format=tar", "-o", str(archive), ref]
            )
            self.shell.run(["tar", "-xf", str(archive), "-C", str(folder)])
            archive.unlink(missing_ok=True)

        self.do(f"unpack {ref} into {folder}", unpack)
        env = self.command_environment() if not self.dry_run else None
        if self.simulation:
            self.do(
                "link the existing python environment and node modules (simulation)",
                lambda: self.link_dependencies(folder),
            )
        else:
            self.do(
                "install the python requirements",
                lambda: (
                    self.shell.run([sys.executable, "-m", "venv", str(folder / ".venv")]),
                    self.shell.run(
                        [str(folder / ".venv/bin/pip"), "install", "-r", "server/requirements.txt"],
                        cwd=folder,
                    ),
                ),
            )
            self.do(
                "install the web packages",
                lambda: self.shell.run(["npm", "ci"], cwd=folder / "web"),
            )
        self.do(
            "build the web app",
            lambda: self.shell.run(
                ["npm", "run", "build"],
                env={**(env or {}), "NODE_ENV": "production"},
                cwd=folder / "web",
            ),
        )
        return folder

    def link_dependencies(self, folder):
        os.symlink(self.source / "server" / ".venv", folder / ".venv")
        # Copied (as hard links where possible), not linked: the web build refuses a link that
        # leaves the release folder.
        shutil.copytree(
            self.source / "web" / "node_modules",
            folder / "web" / "node_modules",
            symlinks=True,
            copy_function=link_or_copy,
        )

    def take_dump(self, release_id):
        """Production only: a dump of the database before anything changes, kept afterwards."""
        values = self.values()
        url = values.get("BACKUP_DATABASE_URL") or values.get("MIGRATION_DATABASE_URL", "")
        target = self.layout.backups / f"before-{release_id}.dump"

        def dump():
            self.layout.backups.mkdir(parents=True, exist_ok=True)
            self.layout.backups.chmod(0o700)
            self.shell.run(
                ["pg_dump", "--format=custom", "--file", str(target)],
                env={**os.environ, **database_environment(url)},
            )
            if target.exists():
                target.chmod(0o600)

        self.do(f"dump the production database to {target} (kept)", dump)

    def migrate(self, folder):
        env = (
            self.command_environment({"DATABASE_ROLE": "migrations"}) if not self.dry_run else None
        )
        self.do(
            "run the database migrations (they must work with the old release too)",
            lambda: self.shell.run(
                [str(folder / ".venv/bin/python"), "manage.py", "migrate", "--noinput"],
                env=env,
                cwd=folder / "server",
            ),
        )

    # ----- services
    def restart_services(self):
        names = [f"bera-{self.layout.env}-{name}" for name in SERVICES]
        if not self.simulation:
            self.do(
                f"restart {', '.join(names)}",
                lambda: self.shell.run([*self.systemctl, "restart", *names]),
            )
            return
        self.say(f"restart the {self.layout.env} processes (local simulation)")
        if not self.dry_run:
            self.restart_local()

    def restart_local(self):
        current = self.layout.current
        env = self.command_environment()
        run_folder = self.layout.base / "run"
        run_folder.mkdir(parents=True, exist_ok=True)
        numbers = RESOURCES[self.layout.env]
        commands = {
            "api": (
                [
                    str(current / ".venv/bin/gunicorn"),
                    "config.wsgi:application",
                    "--bind",
                    f"127.0.0.1:{env['API_PORT']}",
                    "--workers",
                    str(numbers["api_workers"]),
                ],
                current / "server",
                env,
            ),
            "worker": (
                [str(current / ".venv/bin/python"), "manage.py", "qcluster"],
                current / "server",
                {**env, "Q_CLUSTER_WORKERS": str(numbers["queue_workers"])},
            ),
            "web": (
                ["node", "node_modules/next/dist/bin/next", "start", "--port", env["WEB_PORT"]],
                current / "web",
                {**env, "NODE_OPTIONS": f"--max-old-space-size={numbers['web_heap_mb']}"},
            ),
        }
        for name, (argv, cwd, process_env) in commands.items():
            pidfile = run_folder / f"{name}.pid"
            self.stop_local(pidfile)
            self.shell.spawn(
                argv, env=process_env, cwd=cwd, log=run_folder / f"{name}.log", pidfile=pidfile
            )

    def stop_local(self, pidfile):
        if not pidfile.is_file():
            return
        try:
            os.killpg(int(pidfile.read_text()), signal.SIGTERM)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
        pidfile.unlink()
        time.sleep(1)

    def healthy(self):
        values = self.values()
        host = values["ALLOWED_HOSTS"].split(",")[0].strip()
        api = f"http://127.0.0.1:{values['API_PORT']}/api/health/"
        web = f"http://127.0.0.1:{values['WEB_PORT']}/"
        self.say(f"health check: {api} and {web}")
        if self.dry_run:
            return True
        return all(
            self.health(url, host, attempts=HEALTH_ATTEMPTS, delay=HEALTH_DELAY_SECONDS)
            for url in (api, web)
        )

    def prune(self):
        keep = {self.target_of(self.layout.current), self.target_of(self.layout.previous)}
        ids = self.release_ids()
        newest = set(ids[-KEEP_RELEASES:])
        for release_id in ids:
            if release_id not in newest and release_id not in keep:
                self.do(
                    f"delete the old release {release_id}",
                    lambda release_id=release_id: shutil.rmtree(self.layout.releases / release_id),
                )

    # ----- the two commands
    def deploy(self, ref):
        self.preflight()
        release_id = self.new_release_id(ref)
        old = self.target_of(self.layout.current)
        old_previous = self.target_of(self.layout.previous)
        self.say(f"release {release_id} (currently live: {old or 'nothing yet'})")
        folder = self.build_release(ref, release_id)
        if self.layout.env == "production":
            self.take_dump(release_id)
        self.migrate(folder)

        def go_live():
            if old:
                self.switch(self.layout.previous, old)
            self.switch(self.layout.current, release_id)

        self.do(f"switch current to {release_id}", go_live)
        self.restart_services()
        if self.healthy():
            self.prune()
            self.out(
                "Dry run finished: nothing was changed."
                if self.dry_run
                else f"Deployed {release_id}."
            )
            self.out(MIGRATION_REMINDER)
            return True
        return self.fail_back(old, old_previous, release_id)

    def fail_back(self, old, old_previous, release_id):
        self.out(f"FAILED: release {release_id} did not pass the health check.")
        if not old:
            self.out("There is no earlier release to return to; fix it and deploy again.")
            return False
        self.switch(self.layout.current, old)
        if old_previous:  # a rollback after this still goes to the release before the live one
            self.switch(self.layout.previous, old_previous)
        self.restart_services()
        if self.healthy():
            self.out(f"Switched back to {old} by itself; the failed release is kept for study.")
        else:
            self.out(f"Switched back to {old}, but it does not pass the health check either.")
        self.out(MIGRATION_REMINDER)
        return False

    def rollback(self, to=None):
        self.preflight()
        live = self.target_of(self.layout.current)
        target = to or self.target_of(self.layout.previous)
        if not target or not (self.layout.releases / target).is_dir():
            raise DeployError("There is no earlier release to roll back to.")
        self.say(f"roll back from {live} to {target} (the database is not touched)")

        def go():
            self.switch(self.layout.current, target)
            if live and live != target:
                self.switch(self.layout.previous, live)

        self.do(f"switch current to {target}", go)
        self.restart_services()
        ok = self.healthy()
        self.out(f"Rolled back to {target}." if ok else f"Rolled back to {target}: UNHEALTHY.")
        self.out(MIGRATION_REMINDER)
        return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deploy or roll back Bera.")
    parser.add_argument("command", choices=("deploy", "rollback", "units"))
    parser.add_argument("env", choices=ENVIRONMENTS)
    parser.add_argument("--ref", default="HEAD", help="the git ref to deploy")
    parser.add_argument("--to", help="rollback to this release instead of the previous one")
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would happen, change nothing"
    )
    parser.add_argument("--root", default="/srv/bera")
    parser.add_argument("--env-dir", default="/etc/bera")
    parser.add_argument("--out", help="units: the folder to write the service files to")
    parser.add_argument(
        "--simulation",
        action="store_true",
        help="a local simulation: plain processes instead of systemd, existing dependencies",
    )
    arguments = parser.parse_args(argv)
    layout = Layout(Path(arguments.root), arguments.env, Path(arguments.env_dir))
    deployer = Deployer(layout, dry_run=arguments.dry_run, simulation=arguments.simulation)
    try:
        if arguments.command == "units":
            folder = Path(arguments.out or ".")
            folder.mkdir(parents=True, exist_ok=True)
            for name, text in render_units(arguments.env, layout).items():
                (folder / name).write_text(text)
                print(f"wrote {folder / name}")
            return 0
        if arguments.command == "deploy":
            return 0 if deployer.deploy(arguments.ref) else 1
        return 0 if deployer.rollback(arguments.to) else 1
    except DeployError as error:
        print(f"STOPPED: {error}")
        return 1
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"STOPPED: a step failed ({type(error).__name__}); nothing was switched.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
