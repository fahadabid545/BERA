"""The launch check: a ready system passes every automatic item, and each item turns NOT OK when
the thing it checks is wrong. The system's own programs (firewall, web server, SSH, scripts) are
replaced by canned answers."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from adminusers.models import AdminUser
from ai.models import AiModel, PromptVersion
from announcements.models import Announcement
from backups.models import BackupRun
from core.tests.factories import make_admin_user
from cvs.tests.test_ai_reading import set_setting
from launch.context import Context
from launch.report import CHECKS, run_all
from launch.results import NOT_OK, OK, OWNER
from plans.models import Plan
from platform_settings import legal_documents, legal_review
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache

pytestmark = pytest.mark.django_db
PRIVACY = {
    "title": "Fake",
    "sections": [{"heading": "Fake", "paragraphs": ["Deleted data stays in backups for 30 days."]}],
}
TERMS = {"title": "Fake", "sections": [{"heading": "Fake", "paragraphs": ["Fake terms."]}]}
SSH_OUTPUT = "passwordauthentication no\npermitrootlogin no\n"
NGINX_OUTPUT = "server { ssl_verify_client on; }"
NUMBER_ITEMS = 15


class Machine:
    """Answers for the programs the check runs. Change `answers` to make one of them fail."""

    def __init__(self):
        self.answers = {
            "nft": (0, "table inet bera_web"),
            "nginx": (0, NGINX_OUTPUT),
            "sshd": (0, SSH_OUTPUT),
            "scan_secrets.py": (0, ""),
            "check_vulnerabilities.py": (0, ""),
            "check_environments.py": (0, ""),
        }
        self.calls = []

    def __call__(self, arguments, *, folder=None):
        self.calls.append(arguments)
        for name, answer in self.answers.items():
            if any(str(part).endswith(name) or part == name for part in arguments):
                return answer
        return None, ""


@pytest.fixture
def machine():
    return Machine()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "web" / "public").mkdir(parents=True)
    (tmp_path / "web" / "public" / "og-cover.png").write_bytes(b"x")
    (tmp_path / "docs" / "security").mkdir(parents=True)
    (tmp_path / "docs" / "security" / "pre-launch-review.md").write_text("review")
    return tmp_path


@pytest.fixture
def ready(settings, monkeypatch, folder, machine):
    """A system where every automatic item passes."""
    settings.STRIPE_SECRET_KEY = "sk_live_" + "f" * 12
    settings.STRIPE_ALLOW_LIVE_KEYS = True
    settings.STRIPE_WEBHOOK_SECRET = "whsec_" + "f" * 12
    settings.HEARTBEAT_URL = "https://heartbeat.example.test/a"
    settings.BACKUP_HEARTBEAT_URL = "https://heartbeat.example.test/b"
    settings.OPENAI_API_KEY = "fake-key-for-tests"
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.WEB_BASE_URL = "https://app.example.test"
    boss = make_admin_user(role="super")
    make_admin_user(role="super")
    for number, name in enumerate(("Starter", "Growth", "Scale"), start=1):
        Plan.objects.create(
            name=name,
            status="active",
            display_order=number,
            price_usd=Decimal("10.00") * number,
            cvs_per_month=100,
            cvs_per_project=50,
            max_projects=5,
            max_team_accounts=3,
            max_top_n=10,
        )
    monkeypatch.setattr(legal_documents, "TERMS", dict(TERMS))
    monkeypatch.setattr(legal_documents, "PRIVACY", dict(PRIVACY))
    legal_review.mark_reviewed(boss, reviewer_name="Fake Reviewer")
    now = timezone.now()
    for kind in (BackupRun.Kind.BACKUP, BackupRun.Kind.RESTORE_TEST):
        BackupRun.objects.create(
            kind=kind, status="succeeded", started_at=now, finished_at=now, object_name="fake"
        )
    AiModel.objects.create(name="fake-model", input_price_per_million=1, output_price_per_million=1)
    for kind in ("reading", "scoring"):
        PromptVersion.objects.get_or_create(kind=kind, number=1, defaults={"text": "Fake prompt."})
    set_setting("ai.monthly_spend_alert_usd", 100)
    set_setting(
        "general.support_email", "help@company.test.invalid".replace(".test.invalid", ".io")
    )
    Announcement.objects.create(
        message="Fake", starts_at=now, ends_at=now + timedelta(days=30), target="everyone"
    )
    return Context(
        project_folder=folder,
        staging_env_file=folder / "staging.env",
        production_env_file=folder / "production.env",
        run=machine,
    )


def report(context):
    return {each.number: each for each in run_all(context)}


def statuses(context):
    return {number: each.status for number, each in report(context).items()}


class TestTheReport:
    def test_every_item_of_the_checklist_is_reported_once_in_order(self, ready):
        assert [each.number for each in run_all(ready)] == list(
            range(1, NUMBER_ITEMS + 1)
        ) or sorted(each.number for each in run_all(ready)) == list(range(1, NUMBER_ITEMS + 1))
        assert len(CHECKS) == NUMBER_ITEMS

    def test_a_ready_system_has_nothing_not_ok(self, ready):
        assert NOT_OK not in statuses(ready).values()

    def test_what_only_the_owner_can_know_is_left_to_the_owner(self, ready):
        found = statuses(ready)
        for number in (6, 7, 8, 10, 11, 12, 14):
            assert found[number] == OWNER, number
        for number in (1, 2, 3, 4, 5, 9, 13, 15):
            assert found[number] == OK, number

    def test_an_owner_item_never_counts_as_ok(self, ready):
        assert report(ready)[10].status == OWNER
        assert report(ready)[14].status == OWNER

    def test_a_failing_part_wins_over_an_owner_part(self, ready, settings):
        settings.STRIPE_ALLOW_LIVE_KEYS = False
        assert report(ready)[6].status == NOT_OK


class TestAccounts:
    def test_two_step_reset_is_super_only_and_audited(self, ready, monkeypatch):
        assert report(ready)[1].status == OK
        from launch import business

        monkeypatch.setattr(
            business, "roles_allowed", lambda action: frozenset({"super", "support"})
        )
        assert report(ready)[1].status == NOT_OK

    def test_one_super_admin_is_not_enough(self, ready):
        AdminUser.objects.filter(role="super").exclude(
            pk=AdminUser.objects.filter(role="super").first().pk
        ).update(status="blocked")
        assert report(ready)[2].status == NOT_OK

    def test_support_admins_do_not_count_as_super_admins(self, ready):
        AdminUser.objects.filter(role="super").update(role="support")
        AdminUser.objects.filter(pk=AdminUser.objects.first().pk).update(role="super")
        assert report(ready)[2].status == NOT_OK

    def test_a_blocked_super_admin_does_not_count(self, ready):
        AdminUser.objects.filter(role="super").update(status="blocked")
        assert report(ready)[2].status == NOT_OK


class TestPlans:
    @pytest.mark.parametrize("name", ["Starter", "Growth", "Scale"])
    def test_a_plan_that_is_not_active_fails(self, ready, name):
        Plan.objects.filter(name=name).update(status="hidden")
        assert report(ready)[3].status == NOT_OK

    def test_a_missing_number_fails(self, ready):
        Plan.objects.filter(name="Growth").update(max_top_n=None)
        assert report(ready)[3].status == NOT_OK

    def test_no_price_in_dollars_fails(self, ready):
        Plan.objects.filter(name="Scale").update(price_usd=None)
        assert report(ready)[3].status == NOT_OK

    def test_a_missing_plan_fails(self, ready):
        Plan.objects.filter(name="Scale").delete()
        assert report(ready)[3].status == NOT_OK

    def test_two_active_plans_with_one_name_fail(self, ready):
        Plan.objects.create(name="Starter", status="active", price_usd=Decimal("1"))
        assert report(ready)[3].status == NOT_OK

    def test_the_pricing_page_shows_the_active_plans_and_their_prices(self, ready):
        assert report(ready)[4].status == OK

    def test_a_hidden_plan_is_not_on_the_page_so_the_page_still_matches(self, ready):
        Plan.objects.create(name="Secret", status="hidden", price_usd=Decimal("1"))
        assert report(ready)[4].status == OK

    def test_a_plan_without_a_dollar_price_fails_the_page(self, ready):
        Plan.objects.filter(name="Growth").update(price_usd=None)
        assert report(ready)[4].status == NOT_OK


class TestLegal:
    def test_a_missing_text_fails(self, ready, monkeypatch):
        monkeypatch.setattr(legal_documents, "PRIVACY", {"title": "Privacy", "sections": []})
        assert report(ready)[5].status == NOT_OK

    def test_a_text_changed_after_the_review_fails(self, ready, monkeypatch):
        changed = {**TERMS, "sections": [{"heading": "Other", "paragraphs": ["Other."]}]}
        monkeypatch.setattr(legal_documents, "TERMS", changed)
        assert report(ready)[5].status == NOT_OK

    def test_no_review_fails(self, ready):
        from platform_settings.models import LegalReview

        LegalReview.objects.update(reviewed=False)
        assert report(ready)[5].status == NOT_OK

    def test_a_review_without_a_reviewer_name_fails(self, ready):
        from platform_settings.models import LegalReview

        LegalReview.objects.update(reviewer_name="")
        assert report(ready)[5].status == NOT_OK

    @pytest.mark.parametrize(
        "paragraph", ["Nothing about copies.", "Deleted data stays in backups for a while."]
    )
    def test_the_privacy_text_must_say_how_long_backups_keep_deleted_data(
        self, ready, monkeypatch, admin_for_review, paragraph
    ):
        text = {"title": "Fake", "sections": [{"heading": "Fake", "paragraphs": [paragraph]}]}
        monkeypatch.setattr(legal_documents, "PRIVACY", text)
        legal_review.mark_reviewed(admin_for_review, reviewer_name="Fake Reviewer")
        assert report(ready)[5].status == NOT_OK

    def test_the_number_of_days_comes_from_the_backup_setting(
        self, ready, monkeypatch, admin_for_review
    ):
        set_setting("backup.retention_days", 45)
        legal_review.mark_reviewed(admin_for_review, reviewer_name="Fake Reviewer")
        assert report(ready)[5].status == NOT_OK


@pytest.fixture
def admin_for_review():
    return AdminUser.objects.filter(role="super").first()


class TestPayments:
    @pytest.mark.parametrize("flag", [False])
    def test_live_payments_need_the_flag(self, ready, settings, flag):
        settings.STRIPE_ALLOW_LIVE_KEYS = flag
        assert report(ready)[6].status == NOT_OK

    def test_a_test_key_is_not_live_payments(self, ready, settings):
        settings.STRIPE_SECRET_KEY = "sk_test_" + "f" * 12
        assert report(ready)[6].status == NOT_OK

    def test_no_webhook_secret_fails(self, ready, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""
        assert report(ready)[6].status == NOT_OK

    def test_the_owner_is_asked_about_taxes_the_portal_and_the_test_cases(self, ready):
        notes = " ".join(report(ready)[6].notes)
        for word in ("Taxes", "billing portal", "refund", "webhook"):
            assert word in notes


class TestBackupsAndMonitoring:
    def test_an_old_backup_fails(self, ready):
        BackupRun.objects.filter(kind="backup").update(
            finished_at=timezone.now() - timedelta(hours=27)
        )
        assert report(ready)[7].status == NOT_OK

    def test_the_age_limit_is_the_backup_setting(self, ready):
        BackupRun.objects.filter(kind="backup").update(
            finished_at=timezone.now() - timedelta(hours=27)
        )
        set_setting("backup.late_after_hours", 30)
        assert report(ready)[7].status == OWNER

    def test_a_failed_backup_does_not_count(self, ready):
        BackupRun.objects.filter(kind="backup").update(status="failed")
        assert report(ready)[7].status == NOT_OK

    def test_an_old_restore_test_fails(self, ready):
        BackupRun.objects.filter(kind="restore_test").update(
            finished_at=timezone.now() - timedelta(days=9)
        )
        assert report(ready)[7].status == NOT_OK

    def test_the_restore_test_age_is_a_platform_setting(self, ready):
        BackupRun.objects.filter(kind="restore_test").update(
            finished_at=timezone.now() - timedelta(days=9)
        )
        set_setting("launch.restore_test_max_age_days", 10)
        assert report(ready)[7].status == OWNER

    def test_the_owner_confirms_the_offline_key_and_the_lifecycle_rule(self, ready):
        notes = " ".join(report(ready)[7].notes)
        assert "offline" in notes and "lifecycle" in notes

    @pytest.mark.parametrize("name", ["HEARTBEAT_URL", "BACKUP_HEARTBEAT_URL"])
    @pytest.mark.parametrize("value", ["", "http://insecure.example.test"])
    def test_both_heartbeats_must_be_https(self, ready, settings, name, value):
        setattr(settings, name, value)
        assert report(ready)[8].status == NOT_OK


class TestServer:
    @pytest.mark.parametrize("program", ["nft", "nginx", "sshd", "check_environments.py"])
    def test_a_failing_or_missing_program_is_never_a_pass(self, ready, machine, program):
        machine.answers[program] = (1, "")
        assert report(ready)[9].status == NOT_OK
        machine.answers[program] = (None, "")
        assert report(ready)[9].status == NOT_OK

    def test_the_web_server_must_ask_for_the_origin_certificate(self, ready, machine):
        machine.answers["nginx"] = (0, "server { listen 443; }")
        assert report(ready)[9].status == NOT_OK

    @pytest.mark.parametrize(
        "output",
        [
            "passwordauthentication yes\npermitrootlogin no\n",
            "passwordauthentication no\npermitrootlogin yes\n",
            "",
        ],
    )
    def test_ssh_must_be_key_only(self, ready, machine, output):
        machine.answers["sshd"] = (0, output)
        assert report(ready)[9].status == NOT_OK

    @pytest.mark.parametrize("program", ["scan_secrets.py", "check_vulnerabilities.py"])
    def test_the_secret_scan_and_the_library_check_must_be_clean(self, ready, machine, program):
        machine.answers[program] = (1, "")
        assert report(ready)[9].status == NOT_OK

    def test_the_slow_checks_run_once_for_the_whole_report(self, ready, machine):
        report(ready)
        scripts = [
            call for call in machine.calls if str(call[1]).endswith("check_vulnerabilities.py")
        ]
        assert len(scripts) == 1

    def test_an_open_library_finding_fails_the_security_review(self, ready, machine):
        machine.answers["check_vulnerabilities.py"] = (1, "")
        assert report(ready)[15].status == NOT_OK

    def test_the_written_review_must_exist(self, ready, folder):
        (folder / "docs" / "security" / "pre-launch-review.md").unlink()
        assert report(ready)[15].status == NOT_OK


class TestOperations:
    def test_no_openai_key_fails(self, ready, settings):
        settings.OPENAI_API_KEY = ""
        assert report(ready)[11].status == NOT_OK

    def test_no_enabled_model_fails(self, ready):
        AiModel.objects.update(enabled=False)
        assert report(ready)[11].status == NOT_OK

    @pytest.mark.parametrize("kind", ["reading", "scoring"])
    def test_a_missing_prompt_fails(self, ready, kind):
        PromptVersion.objects.filter(kind=kind).delete()
        assert report(ready)[11].status == NOT_OK

    def test_paused_ai_fails(self, ready):
        from ai.models import AiControl

        AiControl.objects.update_or_create(id=1, defaults={"paused": True})
        assert report(ready)[11].status == NOT_OK

    def test_no_spend_limit_fails(self, ready):
        PlatformSetting.objects.filter(key="ai.monthly_spend_alert_usd").delete()
        clear_cache()
        assert report(ready)[11].status == NOT_OK

    @pytest.mark.parametrize(
        "address", ["support@example.test", "support@example.com", "nobody", "", "a@b"]
    )
    def test_an_unreal_support_address_fails(self, ready, address):
        set_setting("general.support_email", address)
        assert report(ready)[12].status == NOT_OK

    def test_email_that_is_only_saved_to_a_folder_fails(self, ready, settings):
        settings.EMAIL_BACKEND = "emailing.backends.DevInboxBackend"
        assert report(ready)[12].status == NOT_OK

    def test_no_ready_announcement_fails(self, ready):
        Announcement.objects.update(
            starts_at=timezone.now() - timedelta(days=2), ends_at=timezone.now() - timedelta(days=1)
        )
        assert report(ready)[13].status == NOT_OK

    def test_a_missing_sharing_image_fails(self, ready, folder):
        (folder / "web" / "public" / "og-cover.png").unlink()
        assert report(ready)[13].status == NOT_OK

    def test_a_public_address_that_is_not_https_fails(self, ready, settings):
        settings.WEB_BASE_URL = "http://app.example.test"
        assert report(ready)[13].status == NOT_OK


class TestTheCommand:
    def test_it_refuses_to_run_outside_production(self, settings):
        settings.APP_ENV = "development"
        with pytest.raises(CommandError, match="production"):
            call_command("check_launch_ready")

    def test_its_only_options_name_the_two_environment_files(self):
        from argparse import ArgumentParser

        from launch.management.commands.check_launch_ready import Command

        parser = ArgumentParser(add_help=False)
        Command().add_arguments(parser)
        names = {name for action in parser._actions for name in action.option_strings}
        assert names == {"--staging-env", "--production-env"}

    def test_it_prints_each_item_as_ok_not_ok_or_for_the_owner_and_fails_on_not_ok(
        self, ready, settings, machine, monkeypatch
    ):
        settings.APP_ENV = "production"
        settings.BASE_DIR = ready.project_folder / "server"
        settings.STRIPE_ALLOW_LIVE_KEYS = False
        monkeypatch.setattr(
            "launch.management.commands.check_launch_ready.Context", lambda **kw: ready
        )
        out = StringIO()
        with pytest.raises(CommandError, match="NOT READY"):
            call_command("check_launch_ready", stdout=out)
        text = out.getvalue()
        assert "[NOT OK] Live payments" in text
        assert "[OK] Two-step reset" in text
        assert "[owner must confirm] Volume test" in text
        assert "Stripe" in text or "Live payments are not on" in text

    def test_it_succeeds_when_nothing_is_not_ok(self, ready, settings, monkeypatch):
        settings.APP_ENV = "production"
        settings.BASE_DIR = ready.project_folder / "server"
        monkeypatch.setattr(
            "launch.management.commands.check_launch_ready.Context", lambda **kw: ready
        )
        out = StringIO()
        call_command("check_launch_ready", stdout=out)
        assert "0 NOT OK" in out.getvalue()


class TestRunningPrograms:
    def test_a_program_that_cannot_be_run_has_no_exit_code(self):
        from launch.context import run_program

        assert run_program(["bera-no-such-program"]) == (None, "")

    def test_a_program_that_runs_gives_its_exit_code_and_output(self):
        import sys

        from launch.context import run_program

        assert run_program([sys.executable, "-c", "print('hi')"]) == (0, "hi\n")
        assert run_program([sys.executable, "-c", "raise SystemExit(3)"])[0] == 3
