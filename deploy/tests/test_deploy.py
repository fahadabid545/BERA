"""The deploy script with a fake shell and fake health check: what it runs, in what order, and
what it does when something fails. Nothing here touches a real server."""

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bera_deploy as deploy
import pytest
from bera_deploy import Deployer, DeployError, Layout

STAGING = Path(__file__).resolve().parents[1] / "env" / "staging.env.example"
PRODUCTION = Path(__file__).resolve().parents[1] / "env" / "production.env.example"


class FakeShell:
    def __init__(self):
        self.commands = []
        self.spawned = []

    def run(self, argv, *, env=None, cwd=None):
        self.commands.append((list(argv), env, cwd))

    def spawn(self, argv, *, env, cwd, log, pidfile):
        self.spawned.append(list(argv))


class Clock:
    def __init__(self):
        self.now = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


@pytest.fixture
def server(tmp_path):
    env_dir = tmp_path / "etc"
    env_dir.mkdir()
    for name, example in (("staging", STAGING), ("production", PRODUCTION)):
        target = env_dir / f"{name}.env"
        target.write_text(example.read_text())
        target.chmod(0o600)
    return tmp_path


def make(server, env="production", *, healthy=(True,), **options):
    lines = []
    answers = list(healthy)
    shell = FakeShell()
    deployer = Deployer(
        Layout(server / "srv", env, server / "etc"),
        shell=shell,
        out=lines.append,
        health=lambda *a, **k: answers.pop(0) if len(answers) > 1 else answers[0],
        service_user="bera",
        owner_of=lambda path: "bera",
        clock=Clock(),
        systemctl=("systemctl",),
        **options,
    )
    return deployer, shell, lines


def release_ids(deployer):
    return deployer.release_ids()


def commands(shell):
    return [" ".join(argv) for argv, _, _ in shell.commands]


class TestADeploy:
    def test_runs_the_steps_in_order_for_production(self, server):
        deployer, shell, _ = make(server)
        assert deployer.deploy("HEAD") is True
        names = commands(shell)
        order = [
            next(i for i, c in enumerate(names) if marker in c)
            for marker in (
                "git -C",
                "pip install",
                "npm ci",
                "npm run build",
                "pg_dump",
                "migrate",
                "systemctl restart",
            )
        ]
        assert order == sorted(order)

    def test_the_new_release_is_live_and_the_old_one_is_kept_as_previous(self, server):
        deployer, _, _ = make(server)
        deployer.deploy("HEAD")
        first = deployer.target_of(deployer.layout.current)
        deployer.deploy("HEAD")
        assert deployer.target_of(deployer.layout.previous) == first
        assert deployer.target_of(deployer.layout.current) != first

    def test_production_takes_a_dump_first_and_keeps_it_private(self, server):
        deployer, shell, _ = make(server)
        deployer.deploy("HEAD")
        dump = next(c for c in shell.commands if c[0][0] == "pg_dump")
        assert str(deployer.layout.backups) in " ".join(dump[0])
        assert stat.S_IMODE(deployer.layout.backups.stat().st_mode) == 0o700

    def test_the_dump_password_is_never_on_the_command_line(self, server):
        deployer, shell, _ = make(server)
        deployer.deploy("HEAD")
        dump = next(c for c in shell.commands if c[0][0] == "pg_dump")
        secret = "fake-production-backup-password"
        assert secret not in " ".join(dump[0])
        assert dump[1]["PGPASSWORD"] == secret

    def test_staging_takes_no_dump(self, server):
        deployer, shell, _ = make(server, "staging")
        deployer.deploy("HEAD")
        assert not any("pg_dump" in c for c in commands(shell))

    def test_migrations_run_with_the_migration_account_before_the_switch(self, server):
        deployer, shell, _ = make(server)
        deployer.deploy("HEAD")
        migrate = next(c for c in shell.commands if "migrate" in c[0])
        assert migrate[1]["DATABASE_ROLE"] == "migrations"
        assert migrate[1]["APP_ENV"] == "production"

    def test_a_failed_migration_switches_nothing(self, server):
        deployer, shell, lines = make(server)
        deployer.deploy("HEAD")
        live = deployer.target_of(deployer.layout.current)

        def fail(argv, *, env=None, cwd=None):
            if "migrate" in argv:
                raise deploy.subprocess.CalledProcessError(1, argv)

        shell.run = fail
        with pytest.raises(deploy.subprocess.CalledProcessError):
            deployer.deploy("HEAD")
        assert deployer.target_of(deployer.layout.current) == live

    def test_prints_the_migration_reminder(self, server):
        deployer, _, lines = make(server)
        deployer.deploy("HEAD")
        assert any("add first, remove only in a later release" in line for line in lines)

    def test_keeps_only_the_last_five_releases(self, server):
        deployer, _, _ = make(server, "staging")
        for _ in range(8):
            deployer.deploy("HEAD")
        kept = release_ids(deployer)
        assert len(kept) == 5
        assert deployer.target_of(deployer.layout.current) == kept[-1]

    def test_never_prunes_the_release_a_rollback_returns_to(self, server):
        deployer, _, _ = make(server, "staging")
        for _ in range(3):
            deployer.deploy("HEAD")
        previous = deployer.target_of(deployer.layout.previous)
        deployer.prune()
        assert previous in release_ids(deployer)


class TestAFailedHealthCheck:
    def test_switches_back_by_itself_and_reports_it(self, server):
        deployer, _, lines = make(server)
        deployer.deploy("HEAD")
        good = deployer.target_of(deployer.layout.current)
        answers = iter([False, True, True, True])
        deployer.health = lambda *a, **k: next(answers)
        assert deployer.deploy("HEAD") is False
        assert deployer.target_of(deployer.layout.current) == good
        text = "\n".join(lines)
        assert "did not pass the health check" in text
        assert f"Switched back to {good} by itself" in text

    def test_a_later_rollback_still_goes_to_the_release_before_the_live_one(self, server):
        deployer, _, _ = make(server)
        deployer.deploy("HEAD")
        older = deployer.target_of(deployer.layout.current)
        deployer.deploy("HEAD")
        live = deployer.target_of(deployer.layout.current)
        answers = iter([False, True, True, True])
        deployer.health = lambda *a, **k: next(answers)
        deployer.deploy("HEAD")
        assert deployer.target_of(deployer.layout.current) == live
        assert deployer.target_of(deployer.layout.previous) == older

    def test_restarts_the_services_again_after_switching_back(self, server):
        deployer, shell, _ = make(server, healthy=(True,))
        deployer.deploy("HEAD")
        restarts = sum("systemctl restart" in c for c in commands(shell))
        answers = iter([False, True, True, True])
        deployer.health = lambda *a, **k: next(answers)
        deployer.deploy("HEAD")
        assert sum("systemctl restart" in c for c in commands(shell)) == restarts + 2

    def test_the_failed_release_is_kept_for_study(self, server):
        deployer, _, _ = make(server)
        deployer.deploy("HEAD")
        answers = iter([False, True, True, True])
        deployer.health = lambda *a, **k: next(answers)
        deployer.deploy("HEAD")
        assert len(release_ids(deployer)) == 2

    def test_a_first_deploy_that_fails_says_there_is_nothing_to_return_to(self, server):
        deployer, _, lines = make(server, healthy=(False,))
        assert deployer.deploy("HEAD") is False
        assert any("no earlier release" in line for line in lines)


class TestARollback:
    def test_returns_to_the_previous_release_and_swaps_the_links(self, server):
        deployer, shell, lines = make(server)
        deployer.deploy("HEAD")
        first = deployer.target_of(deployer.layout.current)
        deployer.deploy("HEAD")
        second = deployer.target_of(deployer.layout.current)
        before = len(shell.commands)
        assert deployer.rollback() is True
        assert deployer.target_of(deployer.layout.current) == first
        assert deployer.target_of(deployer.layout.previous) == second
        # No dump, no migration, no build: only the restart.
        assert [" ".join(c[0]) for c in shell.commands[before:]] == [
            "systemctl restart bera-production-api bera-production-worker bera-production-web"
        ]
        assert any("does not undo database changes" in line for line in lines)

    def test_can_go_back_to_a_named_release(self, server):
        deployer, _, _ = make(server, "staging")
        for _ in range(3):
            deployer.deploy("HEAD")
        oldest = release_ids(deployer)[0]
        deployer.rollback(oldest)
        assert deployer.target_of(deployer.layout.current) == oldest

    def test_refuses_when_there_is_nothing_to_return_to(self, server):
        deployer, _, _ = make(server)
        deployer.deploy("HEAD")
        with pytest.raises(DeployError):
            deployer.rollback()


class TestDryRun:
    def test_prints_the_steps_and_changes_nothing(self, server):
        deployer, shell, lines = make(server, dry_run=True)
        assert deployer.deploy("HEAD") is True
        assert shell.commands == [] and shell.spawned == []
        assert not (server / "srv").exists()
        text = "\n".join(lines)
        assert "[dry-run] would: dump the production database" in text
        assert "Dry run finished: nothing was changed." in text
        assert "Deployed " not in text
        assert "[dry-run] would: run the database migrations" in text
        assert "[dry-run] would: switch current to" in text

    def test_a_rollback_dry_run_changes_nothing(self, server):
        deployer, _, _ = make(server)
        deployer.deploy("HEAD")
        deployer.deploy("HEAD")
        live = deployer.target_of(deployer.layout.current)
        dry, shell, lines = make(server, dry_run=True)
        dry.rollback()
        assert dry.target_of(dry.layout.current) == live
        assert shell.commands == []
        assert any(
            "[dry-run] would: roll back" in line or "would: switch" in line for line in lines
        )


class TestPreflight:
    def test_a_missing_env_file_stops_everything(self, server):
        (server / "etc" / "production.env").unlink()
        layout = Layout(server / "srv", "production", server / "etc")
        with pytest.raises(DeployError, match="does not exist"):
            Deployer(layout, shell=FakeShell(), out=lambda _: None).preflight()

    @pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660])
    def test_an_env_file_others_can_read_stops_everything(self, server, mode):
        (server / "etc" / "production.env").chmod(mode)
        deployer, shell, _ = make(server)
        with pytest.raises(DeployError, match="mode 600"):
            deployer.deploy("HEAD")
        assert shell.commands == []

    def test_the_services_may_not_run_as_root(self, server):
        deployer, _, _ = make(server)
        deployer.service_user = "root"
        with pytest.raises(DeployError, match="root"):
            deployer.preflight()

    def test_the_file_must_belong_to_the_service_user(self, server):
        deployer, _, _ = make(server)
        deployer.owner_of = lambda path: "someone-else"
        with pytest.raises(DeployError, match="service user"):
            deployer.preflight()

    def test_the_file_must_say_which_environment_it_is(self, server):
        path = server / "etc" / "production.env"
        path.write_text(path.read_text().replace("APP_ENV=production", "APP_ENV=staging"))
        deployer, _, _ = make(server)
        with pytest.raises(DeployError, match="APP_ENV"):
            deployer.preflight()

    def test_shared_settings_between_the_two_environments_stop_the_deploy(self, server):
        staging = server / "etc" / "staging.env"
        production = server / "etc" / "production.env"
        shared = [
            line for line in staging.read_text().splitlines() if line.startswith("R2_BUCKET=")
        ][0]
        production.write_text(
            "\n".join(
                shared if line.startswith("R2_BUCKET=") else line
                for line in production.read_text().splitlines()
            )
        )
        deployer, shell, _ = make(server)
        with pytest.raises(DeployError, match="R2_BUCKET") as caught:
            deployer.deploy("HEAD")
        assert shell.commands == []
        assert "fake-bera-staging-bucket" not in str(caught.value)

    def test_no_message_shows_a_secret_value(self, server):
        deployer, _, lines = make(server)
        deployer.deploy("HEAD")
        text = "\n".join(lines)
        for secret in (
            "fake-production-django-secret-key-replace-me",
            "fake-production-app-password",
        ):
            assert secret not in text


class TestTheServiceFiles:
    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_run_as_a_normal_user_with_limits_and_secrets_outside_the_releases(self, server, env):
        layout = Layout(Path("/srv/bera"), env, Path("/etc/bera"))
        units = deploy.render_units(env, layout)
        services = {f"bera-{env}-{name}.service" for name in deploy.SERVICES}
        assert services <= set(units)
        for name, text in units.items():
            if name.endswith(".timer"):
                continue
            assert "User=bera" in text and "User=root" not in text
            assert f"EnvironmentFile=/etc/bera/{env}.env" in text
            assert "NoNewPrivileges=true" in text and "ProtectSystem=strict" in text
            assert "/releases/" not in text  # reached through the `current` link only
            assert "MemoryMax=" in text

    def test_staging_has_no_backup_jobs_and_production_has_three_timers(self):
        staging = deploy.render_units(
            "staging", Layout(Path("/srv/bera"), "staging", Path("/etc/bera"))
        )
        production = deploy.render_units(
            "production", Layout(Path("/srv/bera"), "production", Path("/etc/bera"))
        )
        assert not [name for name in staging if "backup" in name or "restore" in name]
        timers = {name for name in production if name.endswith(".timer")}
        assert timers == {
            "bera-production-backup.timer",
            "bera-production-restore-test.timer",
            "bera-production-backup-check.timer",
        }

    def test_each_backup_job_runs_once_as_the_service_user_with_a_limit(self):
        units = deploy.render_units(
            "production", Layout(Path("/srv/bera"), "production", Path("/etc/bera"))
        )
        for name, command in {
            "backup": "backup_database",
            "restore-test": "verify_backup_restore",
            "backup-check": "check_backup_fresh",
        }.items():
            text = units[f"bera-production-{name}.service"]
            assert "Type=oneshot" in text and "Restart=" not in text
            assert f"manage.py {command}" in text and "User=bera" in text
            assert f"MemoryMax={deploy.RESOURCES['production']['job_memory']}" in text
            assert "Persistent=true" in units[f"bera-production-{name}.timer"]

    def test_the_numbers_come_from_the_one_table(self):
        layout = Layout(Path("/srv/bera"), "production", Path("/etc/bera"))
        units = deploy.render_units("production", layout)
        numbers = deploy.RESOURCES["production"]
        assert f"--workers {numbers['api_workers']}" in units["bera-production-api.service"]
        assert f"MemoryMax={numbers['api_memory']}" in units["bera-production-api.service"]
        assert (
            f"Q_CLUSTER_WORKERS={numbers['queue_workers']}"
            in units["bera-production-worker.service"]
        )
        assert (
            f"max-old-space-size={numbers['web_heap_mb']}" in units["bera-production-web.service"]
        )

    def test_staging_is_smaller_than_production(self):
        staging, production = deploy.RESOURCES["staging"], deploy.RESOURCES["production"]
        assert staging["api_workers"] <= production["api_workers"]
        assert staging["queue_workers"] <= production["queue_workers"]

    def test_the_two_environments_use_different_ports(self):
        first = deploy.read_env_file(STAGING)
        second = deploy.read_env_file(PRODUCTION)
        assert {first["API_PORT"], first["WEB_PORT"]}.isdisjoint(
            {second["API_PORT"], second["WEB_PORT"]}
        )


class TestTheExampleFiles:
    def test_the_examples_are_separate_from_each_other(self):
        from config.separation import compare

        assert compare(deploy.read_env_file(STAGING), deploy.read_env_file(PRODUCTION)) == []

    def test_staging_has_a_folder_and_no_email_account_and_production_the_other_way(self):
        staging, production = deploy.read_env_file(STAGING), deploy.read_env_file(PRODUCTION)
        assert "STAGING_EMAIL_FOLDER" in staging and "EMAIL_HOST" not in staging
        assert "EMAIL_HOST" in production and "STAGING_EMAIL_FOLDER" not in production

    def test_every_required_setting_is_in_the_example_of_its_environment(self):
        from config.secrets import REQUIRED_SETTINGS

        for env, path in (("staging", STAGING), ("production", PRODUCTION)):
            values = deploy.read_env_file(path)
            missing = [
                s.name for s in REQUIRED_SETTINGS if env in s.environments and s.name not in values
            ]
            assert missing == [] or set(missing) <= {"ALLOWED_HOSTS"}, missing

    def test_the_examples_use_test_payment_keys_and_no_live_flag(self):
        for path in (STAGING, PRODUCTION):
            values = deploy.read_env_file(path)
            assert values["STRIPE_SECRET_KEY"].startswith("sk_test_")
            assert "STRIPE_ALLOW_LIVE_KEYS" not in values

    def test_the_nginx_example_matches_the_ports(self):
        conf = (Path(__file__).resolve().parents[1] / "nginx" / "bera.example.conf").read_text()
        for path in (STAGING, PRODUCTION):
            values = deploy.read_env_file(path)
            assert (
                f"127.0.0.1:{values['API_PORT']}" in conf
                and f"127.0.0.1:{values['WEB_PORT']}" in conf
            )
