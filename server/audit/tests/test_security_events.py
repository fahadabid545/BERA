import json
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from audit.alerts import DESCRIPTIONS, TEST_ALERT
from audit.events import KINDS
from audit.models import AlertState, AuditEvent
from audit.security import watch_cv_downloads
from companies.tests.test_invites import setting
from core import rate_limits
from core.tests.factories import make_admin_user, make_company_user, start_session_for
from emailing.models import OutgoingEmail
from emailing.service import deliver_email
from signin import service
from twostep.tests.helpers import person

pytestmark = pytest.mark.django_db


def alerts_to(address):
    """Alerts sent to one address (the address is stored encrypted, so it is matched here)."""
    alerts = OutgoingEmail.objects.filter(template="security_alert").order_by("created_at")
    return [alert for alert in alerts if alert.to_address == address]


def alert_count():
    return OutgoingEmail.objects.filter(template="security_alert").count()


@pytest.fixture
def boss():
    return make_admin_user(role="super", email="boss@example.test", name="Fake Boss")


def reuse_a_refresh_token():
    """Someone presents a refresh token that was already swapped for a new one."""
    owner = make_company_user(role="owner")
    issued = start_session_for(
        user_id=owner.pk, role="owner", company_id=owner.company_id, kind="company"
    )
    service.refresh_session(issued.refresh_token, "company")
    with pytest.raises(Exception):  # noqa: B017 - NotAuthenticated, the normal refusal
        service.refresh_session(issued.refresh_token, "company")
    return owner, issued


class TestEachKindIsRecorded:
    def test_every_security_event_of_the_ticket_has_a_kind(self):
        # failed logins and admin actions were added with the audit log; the rest here.
        for kind in (
            "auth.login_failed",
            "auth.two_step_failed",
            "security.token_reuse",
            "security.permission_refused",
            "security.abuse_blocked",
            "security.download_volume",
            "admin.role_changed",
            "admin.status_changed",
        ):
            assert kind in KINDS
        assert set(DESCRIPTIONS) == {name for name in KINDS if name.startswith("security.")}

    def test_token_reuse_is_recorded_with_who_but_never_the_token(self):
        owner, issued = reuse_a_refresh_token()
        entry = AuditEvent.objects.get(kind="security.token_reuse")
        assert (entry.actor_kind, entry.actor_id, entry.company_id) == (
            "company",
            owner.pk,
            owner.company_id,
        )
        everything = json.dumps(list(AuditEvent.objects.values()), default=str)
        assert issued.refresh_token not in everything and issued.access_token not in everything

    def test_a_refused_request_from_a_signed_in_person_is_recorded(self, settings):
        settings.ROOT_URLCONF = "companies.tests.urls_for_roles"
        member = make_company_user(role="member")
        issued = start_session_for(
            user_id=member.pk, role="member", company_id=member.company_id, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.post("/api/actions/team.invite/").status_code == 403
        entry = AuditEvent.objects.get(kind="security.permission_refused")
        assert (entry.actor_kind, entry.actor_id) == ("company", member.pk)
        assert issued.access_token not in json.dumps(list(AuditEvent.objects.values()), default=str)

    def test_an_allowed_request_and_a_visitor_leave_no_refusal_entry(self, settings):
        settings.ROOT_URLCONF = "companies.tests.urls_for_roles"
        owner = make_company_user(role="owner")
        issued = start_session_for(
            user_id=owner.pk, role="owner", company_id=owner.company_id, kind="company"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.post("/api/actions/team.invite/").status_code == 200
        assert APIClient().post("/api/actions/team.invite/").status_code == 401
        assert not AuditEvent.objects.filter(kind="security.permission_refused").exists()

    def test_an_admin_refused_a_super_admin_action_is_recorded_as_an_admin(self, settings):
        settings.ROOT_URLCONF = "adminusers.tests.urls_for_roles"
        support = make_admin_user(role="support")
        issued = service.start_session(
            user_id=support.pk, role="support", company_id=None, kind="admin"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.post("/api/actions/plan.change/").status_code == 403
        entry = AuditEvent.objects.get(kind="security.permission_refused")
        assert (entry.actor_kind, entry.actor_id) == ("admin", support.pk)

    def test_a_pause_after_wrong_passwords_is_recorded_once_not_per_request(self):
        account = person()
        client = APIClient(REMOTE_ADDR="203.0.113.77")
        for _ in range(8):
            client.post(
                "/api/auth/company/login/",
                {"email": account.email, "password": "wrong-password-123"},
                format="json",
            )
        entries = AuditEvent.objects.filter(kind="security.abuse_blocked")
        assert entries.count() == 1
        assert entries.get().details["why"] == "login_guesses"
        assert AuditEvent.objects.filter(kind="auth.login_failed").count() >= 4

    def test_a_source_blocked_for_hammering_a_limit_is_recorded(self):
        for _ in range(500):
            if rate_limits.hit(rate_limits.LOGIN, "203.0.113.5") and rate_limits.seconds_blocked(
                "203.0.113.5"
            ):
                break
        entries = AuditEvent.objects.filter(kind="security.abuse_blocked")
        assert entries.count() == 1 and entries.get().details["why"] == "rate_limit"
        assert "203.0.113.5" not in json.dumps(list(AuditEvent.objects.values()), default=str)

    def test_more_than_200_downloads_by_one_user_in_an_hour_is_recorded_once(self):
        user, other = make_company_user(), make_company_user()
        for _ in range(200):
            watch_cv_downloads(user)
        assert not AuditEvent.objects.filter(kind="security.download_volume").exists()
        for _ in range(5):
            watch_cv_downloads(user)  # 201 to 205
        entry = AuditEvent.objects.get(kind="security.download_volume")
        assert (entry.actor_id, entry.details) == (user.pk, {"downloads": 201, "limit": 200})
        watch_cv_downloads(other)  # another user has their own count
        assert AuditEvent.objects.filter(kind="security.download_volume").count() == 1

    def test_the_download_limit_follows_the_platform_setting(self):
        setting("security.download_alert_threshold", 3)
        user = make_company_user()
        for _ in range(4):
            watch_cv_downloads(user)
        assert AuditEvent.objects.get(kind="security.download_volume").details["limit"] == 3


class TestAlerts:
    def test_a_security_event_emails_every_active_super_admin(self, boss):
        second = make_admin_user(role="super", email="second@example.test")
        reuse_a_refresh_token()
        assert len(alerts_to("boss@example.test")) == 1
        assert len(alerts_to("second@example.test")) == 1
        assert second.pk != boss.pk

    def test_support_blocked_and_removed_admins_and_company_users_get_nothing(self, boss):
        make_admin_user(role="support", email="support@example.test")
        make_admin_user(role="super", status="blocked", email="blocked@example.test")
        make_admin_user(role="super", status="removed", email="removed@example.test")
        reuse_a_refresh_token()
        recipients = [
            email.to_address for email in OutgoingEmail.objects.filter(template="security_alert")
        ]
        assert recipients == ["boss@example.test"]

    def test_at_most_one_alert_per_kind_per_hour(self, boss):
        reuse_a_refresh_token()
        reuse_a_refresh_token()
        assert alert_count() == 1
        assert AuditEvent.objects.filter(kind="security.token_reuse").count() == 2  # all recorded

    def test_each_kind_has_its_own_hour(self, boss):
        reuse_a_refresh_token()
        rate_limits.block("someone", 60)
        assert alert_count() == 2

    def test_after_the_hour_the_next_event_alerts_again(self, boss):
        reuse_a_refresh_token()
        AlertState.objects.update(last_sent_at=timezone.now() - timedelta(minutes=61))
        reuse_a_refresh_token()
        assert alert_count() == 2

    def test_just_under_the_hour_still_holds_it_back(self, boss):
        reuse_a_refresh_token()
        AlertState.objects.update(last_sent_at=timezone.now() - timedelta(minutes=59))
        reuse_a_refresh_token()
        assert alert_count() == 1

    def test_the_hour_follows_the_platform_setting(self, boss):
        setting("security.alert_cooldown_minutes", 5)
        reuse_a_refresh_token()
        AlertState.objects.update(last_sent_at=timezone.now() - timedelta(minutes=6))
        reuse_a_refresh_token()
        assert alert_count() == 2

    def test_with_no_active_super_admin_the_event_is_recorded_and_nothing_is_sent(self):
        make_admin_user(role="support")
        reuse_a_refresh_token()
        assert AuditEvent.objects.filter(kind="security.token_reuse").count() == 1
        assert alert_count() == 0 and not AlertState.objects.exists()

    def test_an_admin_who_appears_later_is_alerted_for_the_next_event(self):
        reuse_a_refresh_token()
        make_admin_user(role="super", email="late@example.test")
        reuse_a_refresh_token()
        assert len(alerts_to("late@example.test")) == 1

    def test_the_alert_says_what_happened_and_holds_no_secret_or_private_detail(self, boss):
        owner, issued = reuse_a_refresh_token()
        email = alerts_to("boss@example.test")[0]
        assert email.subject == "Bera security alert"
        assert DESCRIPTIONS["security.token_reuse"] in email.text_body
        assert "/admin/settings/audit-log" in email.text_body
        for private in (issued.refresh_token, issued.access_token, owner.email, owner.name):
            assert private not in email.text_body and private not in email.html_body

    def test_the_alert_is_really_delivered_to_the_inbox(self, boss):
        reuse_a_refresh_token()
        mail.outbox.clear()
        deliver_email(str(alerts_to("boss@example.test")[0].id))
        assert [m.to for m in mail.outbox] == [["boss@example.test"]]
        assert mail.outbox[0].subject == "Bera security alert"


class TestTheTestAlert:
    def test_it_reaches_every_active_super_admin_even_during_the_hour(self, boss):
        make_admin_user(role="super", email="second@example.test")
        make_admin_user(role="support", email="support@example.test")
        reuse_a_refresh_token()  # uses up the hour for token reuse
        before = alert_count()
        call_command("send_test_security_alert")
        assert alert_count() == before + 2
        sent = alerts_to("boss@example.test")[-1]
        assert TEST_ALERT in sent.text_body
        assert alerts_to("support@example.test") == []

    def test_a_test_alert_arrives_by_email(self, boss):
        call_command("send_test_security_alert")
        mail.outbox.clear()
        deliver_email(str(alerts_to("boss@example.test")[0].id))
        assert mail.outbox[0].to == ["boss@example.test"]
        assert TEST_ALERT in mail.outbox[0].body

    def test_it_says_when_there_is_nobody_to_tell(self, capsys):
        call_command("send_test_security_alert")
        assert "0 super admin" in capsys.readouterr().out
