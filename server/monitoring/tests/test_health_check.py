import logging
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from audit.alerts import DESCRIPTIONS, MONITORING_KINDS
from audit.events import KINDS
from audit.models import AuditEvent
from companies.tests.test_invites import setting
from core.tests.factories import make_admin_user
from cvs.tests.test_processing import Tenant, make_plan
from emailing.models import OutgoingEmail
from emailing.service import deliver_email
from monitoring import readings, service
from monitoring.errors import count_server_error
from monitoring.models import CheckStreak, ErrorCount

pytestmark = pytest.mark.django_db
ADDRESS = "https://hc-ping.example.test/fake-check-0001"  # nosecret: fake


@pytest.fixture(autouse=True)
def calm_server(monkeypatch, settings):
    """A healthy server by default; each test makes one thing wrong. Pings are recorded."""
    monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 40.0)
    monkeypatch.setattr(readings, "memory_used_percent", lambda meminfo=None: 40.0)
    settings.HEARTBEAT_URL = ADDRESS
    pings = []
    monkeypatch.setattr(service, "ping", lambda address: pings.append(address) or True)
    return pings


@pytest.fixture
def boss():
    return make_admin_user(role="super", email="boss@example.test", name="Fake Boss")


def alerts():
    return OutgoingEmail.objects.filter(template="security_alert")


def alert_text():
    assert alerts().count() == 1
    deliver_email(alerts().get().pk)
    return mail.outbox[-1].body


def run(times=1):
    for _ in range(times):
        result = service.run_health_check()
    return result


def entries(kind):
    return AuditEvent.objects.filter(kind=kind)


class TestAHealthyServer:
    def test_nothing_is_alerted_and_the_ping_is_sent(self, boss, calm_server):
        measurements, fine = run()
        assert fine and calm_server == [ADDRESS]
        assert alerts().count() == 0 and not AuditEvent.objects.filter(kind__startswith="monitor.")
        assert {m.name for m in measurements} >= {"disk", "memory", "jobs_waiting", "error_rate"}

    def test_the_ping_carries_only_the_address(self, calm_server):
        run()
        assert calm_server == [ADDRESS]  # one call, with nothing but the address

    def test_with_no_address_set_nothing_is_sent_and_it_is_still_fine(self, settings, monkeypatch):
        settings.HEARTBEAT_URL = ""
        monkeypatch.undo()
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 40.0)
        monkeypatch.setattr(readings, "memory_used_percent", lambda meminfo=None: 40.0)
        assert run()[1] is True


class TestTheStreakRule:
    """Disk and memory alert only after the limit was passed three checks in a row."""

    @pytest.mark.parametrize(
        ("reading", "event", "words"),
        [
            ("disk_used_percent", "monitor.disk_full", "Now: 91% used."),
            ("memory_used_percent", "monitor.memory_low", "Now: 95% in use."),
        ],
    )
    def test_the_alert_fires_on_the_third_check_and_not_before(
        self, monkeypatch, boss, reading, event, words
    ):
        value = 91.0 if reading == "disk_used_percent" else 95.0
        monkeypatch.setattr(readings, reading, lambda *a, **k: value)
        run(2)
        assert alerts().count() == 0 and not entries(event).exists()
        run()
        assert alerts().count() == 1 and entries(event).count() == 1
        assert words in alert_text()

    def test_the_audit_entry_holds_two_numbers_and_nothing_else(self, monkeypatch, boss):
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.4)
        run(3)
        assert entries("monitor.disk_full").get().details == {"value": 91, "limit": 85}

    def test_a_dip_in_between_starts_the_count_again(self, monkeypatch, boss):
        values = iter([91.0, 91.0, 40.0, 91.0, 91.0])
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: next(values))
        run(5)
        assert alerts().count() == 0
        assert CheckStreak.objects.get(name="disk").consecutive == 2

    def test_staying_over_the_limit_alerts_again_only_after_the_cooldown(self, monkeypatch, boss):
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.0)
        run(8)
        assert alerts().count() == 1 and entries("monitor.disk_full").count() == 1

    def test_the_number_of_checks_is_a_setting(self, monkeypatch, boss):
        setting("monitor.checks_in_a_row", 1)
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.0)
        run()
        assert alerts().count() == 1

    def test_the_limit_is_a_setting(self, monkeypatch, boss):
        setting("monitor.disk_used_percent_limit", 95)
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.0)
        assert run(3)[1] is True and alerts().count() == 0

    def test_exactly_at_the_limit_is_still_fine(self, monkeypatch, boss):
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 85.0)
        assert run(4)[1] is True


class TestBackgroundJobs:
    @pytest.fixture
    def tenant(self):
        return Tenant(make_plan())

    def test_too_many_waiting_jobs_alert(self, tenant, boss):
        setting("monitor.waiting_jobs_limit", 2)
        for _ in range(3):
            tenant.cv()
        run(3)
        assert entries("monitor.jobs_waiting").get().details == {"value": 3, "limit": 2}
        assert "Now: 3 jobs waiting." in alert_text()

    def test_a_retry_that_is_not_due_yet_is_not_waiting_too_long(self, tenant, boss):
        setting("monitor.waiting_jobs_limit", 1)
        for _ in range(3):
            tenant.cv(next_attempt_at=timezone.now() + timedelta(hours=1))
        assert run(3)[1] is True

    def test_a_job_that_waited_too_long_alerts_with_the_minutes(self, tenant, boss):
        tenant.cv(next_attempt_at=timezone.now() - timedelta(minutes=45))
        run(3)
        assert entries("monitor.job_waiting_too_long").exists()
        assert "Now: 45 minutes the longest job has waited." in alert_text()

    def test_stuck_jobs_alert(self, tenant, boss):
        setting("monitor.stuck_jobs_limit", 1)
        for _ in range(2):
            tenant.cv(status="reading", started_at=timezone.now() - timedelta(minutes=30))
        run(3)
        assert entries("monitor.jobs_stuck").get().details == {"value": 2, "limit": 1}

    def test_work_held_back_on_purpose_while_ai_is_paused_is_not_an_alert(self, tenant, boss):
        from ai import control
        from ai.tests.test_model_settings import REASON

        control.pause(boss_admin(), REASON)
        setting("monitor.waiting_jobs_limit", 1)
        for _ in range(3):
            tenant.cv(next_attempt_at=timezone.now() - timedelta(hours=2))
        assert run(4)[1] is True and alerts().count() == 0

    def test_nothing_in_the_alert_names_a_company_or_a_file(self, tenant, boss):
        setting("monitor.waiting_jobs_limit", 1)
        for _ in range(2):
            tenant.cv()
        run(3)
        everything = alert_text() + str(list(AuditEvent.objects.values()))
        assert tenant.company.name not in everything


def boss_admin():
    from adminusers.models import AdminUser

    return AdminUser.objects.filter(role="super").first()


class TestQueuedEmails:
    def queue(self, minutes_old, count=1):
        for _ in range(count):
            row = OutgoingEmail.objects.create(
                template="welcome", to_address="user@example.test", subject="s",
                text_body="t", html_body="h",
            )  # fmt: skip
            OutgoingEmail.objects.filter(pk=row.pk).update(
                created_at=timezone.now() - timedelta(minutes=minutes_old)
            )

    def test_emails_stuck_in_the_queue_alert(self, boss):
        self.queue(minutes_old=40, count=11)
        run(3)
        assert entries("monitor.emails_backed_up").get().details == {"value": 11, "limit": 10}

    def test_recent_emails_are_just_work_in_progress(self, boss):
        self.queue(minutes_old=2, count=50)
        assert run(3)[1] is True


class TestServerErrors:
    def test_a_burst_alerts_on_the_first_check_with_the_count(self, boss):
        for _ in range(11):
            count_server_error()
        run()
        assert entries("monitor.error_rate").get().details == {"value": 11, "limit": 10}
        assert "Now: 11 server errors in 5 minutes." in alert_text()

    def test_one_error_or_a_few_do_not_alert(self, boss):
        for _ in range(10):
            count_server_error()
        assert run(2)[1] is True and alerts().count() == 0

    def test_errors_older_than_the_window_do_not_count(self, boss):
        ErrorCount.objects.create(minute=timezone.now() - timedelta(minutes=20), count=500)
        assert run()[1] is True

    def test_the_window_and_the_limit_are_settings(self, boss):
        setting("monitor.error_limit", 2)
        setting("monitor.error_window_minutes", 30)
        ErrorCount.objects.create(minute=timezone.now() - timedelta(minutes=20), count=3)
        run()
        assert entries("monitor.error_rate").exists()

    def test_old_counts_are_forgotten(self):
        ErrorCount.objects.create(minute=timezone.now() - timedelta(days=3), count=9)
        run()
        assert ErrorCount.objects.count() == 0

    def test_counting_keeps_only_a_number(self):
        count_server_error()
        count_server_error()
        row = ErrorCount.objects.get()
        assert row.count == 2 and {f.name for f in ErrorCount._meta.fields} == {"minute", "count"}

    def test_an_unexpected_error_in_the_api_is_counted(self):
        from core.exception_handler import api_exception_handler

        api_exception_handler(RuntimeError("secret detail"), {})
        assert ErrorCount.objects.get().count == 1
        assert "secret detail" not in str(list(ErrorCount.objects.values()))

    def test_a_server_side_app_error_counts_and_a_refusal_does_not(self):
        from core.errors import AppError
        from core.exception_handler import api_exception_handler

        api_exception_handler(AppError("x", "Broken.", status_code=503), {})
        api_exception_handler(AppError("y", "No.", status_code=400), {})
        assert ErrorCount.objects.get().count == 1

    def test_an_error_page_outside_the_api_is_counted(self, rf):
        from core.views import server_error

        assert server_error(rf.get("/")).status_code == 500
        assert ErrorCount.objects.get().count == 1

    def test_counting_never_makes_things_worse_when_the_database_fails(self, monkeypatch, caplog):
        def broken(*args, **kwargs):
            raise RuntimeError("connection to 10.0.0.5 refused")

        monkeypatch.setattr(ErrorCount.objects, "filter", broken)
        with caplog.at_level(logging.WARNING):
            count_server_error()  # does not raise
        assert "RuntimeError" in caplog.text and "10.0.0.5" not in caplog.text


class TestThePing:
    def test_a_check_over_its_limit_stops_the_ping_at_once(self, monkeypatch, boss, calm_server):
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.0)
        _, fine = run()  # the first run: no alert yet, but no ping either
        assert not fine and calm_server == [] and alerts().count() == 0

    def test_each_check_stops_it(self, monkeypatch, boss, calm_server):
        monkeypatch.setattr(readings, "memory_used_percent", lambda meminfo=None: 99.0)
        assert run()[1] is False and calm_server == []

    def test_a_failed_ping_means_not_fine(self, monkeypatch):
        monkeypatch.setattr(service, "ping", lambda address: False)
        assert run()[1] is False

    def test_the_command_exits_with_an_error_when_not_fine(self, monkeypatch, boss):
        monkeypatch.setattr(readings, "disk_used_percent", lambda paths=None: 91.0)
        with pytest.raises(CommandError):
            call_command("check_system_health")

    def test_the_command_lists_each_check_without_data(self, capsys):
        call_command("check_system_health")
        output = capsys.readouterr().out
        assert "ok   disk: 40% used" in output and "ok   error_rate" in output


class TestTheTestCommand:
    def test_every_alert_is_sent_once_to_every_super_admin_and_nothing_is_recorded(self, boss):
        second = make_admin_user(role="super", email="second@example.test")
        make_admin_user(role="support", email="support@example.test")
        call_command("send_test_monitoring_alert")
        assert alerts().count() == len(MONITORING_KINDS) * 2
        assert not AuditEvent.objects.filter(kind__startswith="monitor.").exists()
        assert second.pk != boss.pk
        deliver_email(alerts().first().pk)
        assert "This is a test." in mail.outbox[-1].body

    def test_the_cooldown_does_not_hold_the_test_back(self, boss):
        call_command("send_test_monitoring_alert")
        call_command("send_test_monitoring_alert")
        assert alerts().count() == len(MONITORING_KINDS) * 2


def test_every_monitoring_alert_has_a_wording_and_an_audit_kind():
    assert len(MONITORING_KINDS) == 7
    for kind in MONITORING_KINDS:
        assert kind in KINDS and DESCRIPTIONS[kind].endswith(".")
