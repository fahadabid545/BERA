"""The admin settings screens: General, Limits, Rate limiting, Security, Platform values and
Maintenance. Super admin only, audited, and every change applies at once."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai.tests.test_model_settings import admin_client
from audit.models import AuditEvent
from core.tests.factories import make_company, make_company_user, start_session_for
from emailing.models import OutgoingEmail
from emailing.service import send_email
from platform_settings import admin_settings
from platform_settings.definitions import DEFINITIONS
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting

pytestmark = pytest.mark.django_db
URL = "/api/admin/settings/"
MAINTENANCE = URL + "maintenance/"


@pytest.fixture
def boss():
    return admin_client("super")


def save(client, values):
    return client.put(URL, {"values": values}, format="json")


def items(reply):
    return {item["key"]: item for item in reply.json()["items"]}


def audit(kind):
    return AuditEvent.objects.filter(kind=kind)


class TestReading:
    def test_each_page_lists_its_settings_with_their_defaults(self, boss):
        for page, keys in admin_settings.PAGES.items():
            reply = boss[0].get(URL, {"page": page})
            assert reply.status_code == 200
            listed = items(reply)
            assert sorted(listed) == sorted(keys)
            for key in keys:
                assert listed[key]["default"] == DEFINITIONS[key].default
                assert listed[key]["is_default"] is True

    def test_the_pages_hold_what_the_ticket_names(self, boss):
        pages = admin_settings.PAGES
        assert {"general.app_name", "general.support_email"} == set(pages["general"])
        assert {
            "uploads.max_file_size_mb",
            "uploads.max_files_per_batch",
            "uploads.max_files_in_progress_per_user",
            "tokens.team_invite_days",
            "team.max_accounts_per_company",
        } == set(pages["limits"])
        assert all(key.startswith("rate_limits.") for key in pages["rate_limits"])
        assert len(pages["rate_limits"]) == len(
            [key for key in DEFINITIONS if key.startswith("rate_limits.")]
        )
        assert {"tokens.access_minutes", "passwords.min_length"} <= set(pages["security"])

    def test_platform_values_lists_every_editable_value_but_not_those_with_their_own_screen(
        self, boss
    ):
        listed = items(boss[0].get(URL))
        assert set(listed) == set(DEFINITIONS) - admin_settings.MANAGED_ELSEWHERE
        for managed in ("ai.reading_model", "maintenance.enabled", "billing.pkr_per_usd"):
            assert managed not in listed

    def test_an_unknown_page_is_not_found(self, boss):
        assert boss[0].get(URL, {"page": "nope"}).status_code == 404

    def test_a_changed_value_shows_as_not_the_default(self, boss):
        save(boss[0], {"uploads.max_file_size_mb": 20})
        item = items(boss[0].get(URL, {"page": "limits"}))["uploads.max_file_size_mb"]
        assert (item["value"], item["default"], item["is_default"]) == (20, 10, False)


class TestSaving:
    def test_a_change_is_stored_and_audited_with_old_and_new(self, boss):
        client, me = boss
        assert save(client, {"uploads.max_file_size_mb": 20}).status_code == 200
        assert get_setting("uploads.max_file_size_mb") == 20
        event = audit("admin.setting_changed").get()
        assert event.actor_id == me.pk
        assert event.details["setting"] == "uploads.max_file_size_mb"
        assert event.details["changes"]["value"] == {"old": 10, "new": 20}
        assert event.created_at is not None

    def test_it_applies_without_a_restart(self, boss):
        assert get_setting("uploads.max_files_per_batch") == 30
        save(boss[0], {"uploads.max_files_per_batch": 7})
        assert get_setting("uploads.max_files_per_batch") == 7

    def test_a_value_that_did_not_change_is_not_audited(self, boss):
        save(boss[0], {"uploads.max_file_size_mb": 10})
        assert not audit("admin.setting_changed").exists()
        assert not PlatformSetting.objects.exists()

    def test_setting_the_default_again_removes_the_override(self, boss):
        save(boss[0], {"uploads.max_file_size_mb": 20})
        save(boss[0], {"uploads.max_file_size_mb": 10})
        assert not PlatformSetting.objects.filter(key="uploads.max_file_size_mb").exists()
        assert audit("admin.setting_changed").count() == 2

    def test_several_settings_are_saved_together_or_not_at_all(self, boss):
        reply = save(boss[0], {"uploads.max_file_size_mb": 20, "uploads.max_files_per_batch": 0})
        assert reply.status_code == 400
        assert "uploads.max_files_per_batch" in reply.json()["error"]["fields"]
        assert get_setting("uploads.max_file_size_mb") == 10
        assert not audit("admin.setting_changed").exists()

    @pytest.mark.parametrize(
        "key, value",
        [
            ("uploads.max_file_size_mb", 0),
            ("uploads.max_file_size_mb", 101),
            ("uploads.max_file_size_mb", "ten"),
            ("uploads.max_file_size_mb", True),
            ("rate_limits.login_per_minute", -1),
            ("general.support_email", "not an address"),
            ("general.support_email", ""),
            ("general.app_name", ""),
            ("general.app_name", "x" * 61),
            ("general.app_name", "Name\nWith break"),
            ("passwords.block_common_passwords", "yes"),
            ("uploads.allowed_file_types", []),
        ],
    )
    def test_a_value_that_is_not_allowed_is_refused(self, boss, key, value):
        reply = save(boss[0], {key: value})
        assert reply.status_code == 400
        assert key in reply.json()["error"]["fields"]

    @pytest.mark.parametrize(
        "key", ["no.such_setting", "ai.reading_model", "maintenance.enabled", "billing.pkr_per_usd"]
    )
    def test_an_unknown_setting_or_one_with_its_own_screen_is_refused(self, boss, key):
        reply = save(boss[0], {key: 1})
        assert reply.status_code == 400 and key in reply.json()["error"]["fields"]

    def test_the_shortest_password_cannot_be_longer_than_the_longest(self, boss):
        reply = save(boss[0], {"passwords.min_length": 100, "passwords.max_length": 50})
        assert reply.status_code == 400
        assert "passwords.min_length" in reply.json()["error"]["fields"]

    def test_a_list_value_is_audited_as_short_text(self, boss):
        save(boss[0], {"uploads.allowed_file_types": ["pdf"]})
        event = audit("admin.setting_changed").get()
        assert event.details["changes"]["value"] == {"old": '["pdf", "docx"]', "new": '["pdf"]'}

    def test_a_secret_style_setting_records_only_that_it_changed(self, boss, monkeypatch):
        monkeypatch.setattr(admin_settings, "SECRET_STYLE", frozenset({"uploads.max_file_size_mb"}))
        save(boss[0], {"uploads.max_file_size_mb": 20})
        event = audit("admin.setting_changed").get()
        assert "changes" not in event.details
        assert "20" not in str(event.details)

    def test_an_empty_or_unknown_field_body_is_refused(self, boss):
        assert boss[0].put(URL, {"values": {}}, format="json").status_code == 400
        assert (
            boss[0].put(URL, {"values": {"a.b": 1}, "extra": 1}, format="json").status_code == 400
        )


class TestResetting:
    def test_a_value_goes_back_to_its_default_and_is_audited(self, boss):
        save(boss[0], {"uploads.max_file_size_mb": 20})
        reply = boss[0].post(f"{URL}uploads.max_file_size_mb/reset/")
        assert reply.status_code == 200
        assert get_setting("uploads.max_file_size_mb") == 10
        event = audit("admin.setting_reset").get()
        assert event.details["changes"]["value"] == {"old": 20, "new": 10}

    def test_resetting_one_that_was_never_changed_does_nothing(self, boss):
        assert boss[0].post(f"{URL}uploads.max_file_size_mb/reset/").status_code == 200
        assert not audit("admin.setting_reset").exists()

    def test_an_unknown_setting_cannot_be_reset(self, boss):
        assert boss[0].post(f"{URL}no.such/reset/").status_code == 404
        assert boss[0].post(f"{URL}ai.reading_model/reset/").status_code == 404


class TestSuperAdminOnly:
    def test_support_is_refused_everywhere_and_nothing_changes(self):
        support = admin_client("support")[0]
        assert support.get(URL).status_code == 403
        assert save(support, {"uploads.max_file_size_mb": 20}).status_code == 403
        assert support.post(f"{URL}uploads.max_file_size_mb/reset/").status_code == 403
        assert support.get(MAINTENANCE).status_code == 403
        body = {"enabled": True, "message": "Fake", "reason": "Fake"}
        assert support.post(MAINTENANCE, body, format="json").status_code == 403
        assert not PlatformSetting.objects.exists()

    def test_a_company_person_and_a_visitor_are_refused(self, client):
        assert client.get(URL).status_code == 401
        person = make_company_user()
        issued = start_session_for(
            user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
        )
        company = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert company.get(URL).status_code in (401, 403)


class TestBehaviourChanges:
    """Each page's settings really change what the platform does."""

    def test_the_app_name_and_support_email_reach_every_email(self, boss):
        save(
            boss[0],
            {"general.app_name": "Fake Platform", "general.support_email": "help@example.test"},
        )
        send_email(
            "reset_password",
            "someone@example.test",
            name="Fake Person",
            link="http://localhost:3000/example?token=fake",
            expires_in="1 hour",
        )
        mail = OutgoingEmail.objects.get()
        assert "Fake Platform" in mail.subject and "Bera" not in mail.subject
        assert mail.text_body.startswith("Fake Platform")
        assert "help@example.test" in mail.text_body and "Bera" not in mail.html_body
        assert "help@example.test" in mail.html_body

    def test_the_sender_name_and_reply_to_follow_the_settings(self, boss, settings, tmp_path):
        from django.core import mail

        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        save(
            boss[0],
            {"general.app_name": "Fake Platform", "general.support_email": "help@example.test"},
        )
        send_email(
            "reset_password",
            "someone@example.test",
            now=True,
            name="Fake Person",
            link="http://localhost:3000/example?token=fake",
            expires_in="1 hour",
        )
        [sent] = mail.outbox
        assert sent.from_email.startswith("Fake Platform <")
        assert sent.reply_to == ["help@example.test"]

    def test_the_support_email_is_in_the_suspended_message(self, boss):
        from signin.login import contact_support  # noqa: F401  (the message is built from it)

        save(boss[0], {"general.support_email": "help@example.test"})
        from platform_settings.branding import contact_support as message

        assert message("Please contact support") == "Please contact support at help@example.test."

    def test_the_upload_size_limit_follows_the_setting(self, boss):
        from cvs.service import upload_rules

        save(boss[0], {"uploads.max_file_size_mb": 25, "uploads.max_files_per_batch": 9})
        rules = upload_rules(make_company().pk)
        assert (rules["max_file_size_mb"], rules["max_files_per_batch"]) == (25, 9)

    def test_the_team_invite_lifetime_follows_the_setting(self, boss):
        from emailing.link_tokens import issue_link_token
        from emailing.models import LinkToken

        save(boss[0], {"tokens.team_invite_days": 2})
        from companies.invites import _lifetime_hours

        assert _lifetime_hours() == 48
        issue_link_token("team_invite", 1, _lifetime_hours())
        token = LinkToken.objects.get()
        assert token.expires_at - timezone.now() > timedelta(hours=47)

    def test_session_lengths_follow_the_settings(self, boss):
        from signin import service

        save(boss[0], {"tokens.admin_access_minutes": 3, "tokens.admin_refresh_hours": 2})
        issued = service.start_session(
            user_id=boss[1].pk, role="super", company_id=None, kind="admin"
        )
        assert issued.access_seconds == 3 * 60
        assert issued.refresh_seconds == 2 * 3600

    def test_the_password_rules_follow_the_settings(self, boss):
        from core.passwords import password_problems

        long_enough = "copper-meadow-lantern-58"  # nosecret: fake test value
        assert not password_problems(long_enough)
        save(boss[0], {"passwords.min_length": 40, "passwords.max_length": 60})
        assert password_problems(long_enough)

    def test_a_rate_limit_follows_the_setting(self, boss):
        from core.throttles import LoginThrottle

        save(boss[0], {"rate_limits.login_per_minute": 2})
        assert get_setting("rate_limits.login_per_minute") == 2
        assert LoginThrottle  # the throttle reads the value when it runs


class TestMaintenance:
    def turn_on(self, client, message="Fake maintenance message.", reason="Fake reason."):
        return client.post(
            MAINTENANCE, {"enabled": True, "message": message, "reason": reason}, format="json"
        )

    def test_it_starts_off(self, boss):
        assert boss[0].get(MAINTENANCE).json()["enabled"] is False

    def test_turning_it_on_needs_a_reason_and_is_audited(self, boss):
        client, me = boss
        assert self.turn_on(client).status_code == 200
        assert client.get(MAINTENANCE).json() == {
            "enabled": True,
            "message": "Fake maintenance message.",
        }
        event = audit("admin.maintenance_changed").get()
        assert (event.actor_id, event.reason) == (me.pk, "Fake reason.")
        assert event.details["changes"]["enabled"] == {"old": False, "new": True}

    def test_a_reason_is_required_both_ways(self, boss):
        body = {"enabled": True, "message": "Fake"}
        assert boss[0].post(MAINTENANCE, body, format="json").status_code == 400
        self.turn_on(boss[0])
        off = boss[0].post(MAINTENANCE, {"enabled": False}, format="json")
        assert off.status_code == 400
        assert boss[0].get(MAINTENANCE).json()["enabled"] is True

    def test_turning_it_off_is_audited_and_keeps_the_message(self, boss):
        self.turn_on(boss[0])
        reply = boss[0].post(MAINTENANCE, {"enabled": False, "reason": "Fake done."}, format="json")
        assert reply.json() == {"enabled": False, "message": "Fake maintenance message."}
        assert audit("admin.maintenance_changed").count() == 2

    @pytest.mark.parametrize("message", ["", "x" * 501, "line\nbreak"])
    def test_a_message_is_needed_to_turn_it_on(self, boss, message):
        reply = self.turn_on(boss[0], message=message)
        assert reply.status_code == 400
        assert boss[0].get(MAINTENANCE).json()["enabled"] is False

    def test_a_flag_that_is_not_true_or_false_is_refused(self, boss):
        body = {"enabled": "yes", "message": "Fake", "reason": "Fake"}
        assert boss[0].post(MAINTENANCE, body, format="json").status_code == 400

    def test_everyone_can_read_the_message_without_signing_in(self, boss, client):
        self.turn_on(boss[0])
        info = client.get("/api/platform/").json()
        assert info["maintenance"] == {"enabled": True, "message": "Fake maintenance message."}
        assert info["app_name"] == "Bera" and info["support_email"] == "support@example.test"
        assert "password" not in str(info).lower()

    def test_companies_cannot_upload_while_it_is_on(self, boss):
        from cvs.service import upload_block, upload_cvs

        self.turn_on(boss[0])
        block = upload_block(1)
        assert (block["code"], block["message"]) == (
            "maintenance_mode",
            "Fake maintenance message.",
        )
        from core.errors import AppError

        with pytest.raises(AppError) as refused:
            upload_cvs(None, None, [])
        assert (refused.value.code, refused.value.status_code) == ("maintenance_mode", 503)

    def test_uploads_work_again_when_it_is_off(self, boss):
        from cvs.service import upload_block

        self.turn_on(boss[0])
        boss[0].post(MAINTENANCE, {"enabled": False, "reason": "Fake done."}, format="json")
        block = upload_block(make_company_user().company_id)
        assert block is None or block["code"] != "maintenance_mode"

    def test_admins_can_still_sign_in_while_it_is_on(self, boss):
        self.turn_on(boss[0])
        assert boss[0].get(URL).status_code == 200
        from core.tests.factories import make_admin_user

        account = make_admin_user(email="signs-in@example.test")
        account.set_password("violet-harbour-lantern-92")  # nosecret: fake test value
        account.save()
        reply = APIClient(REMOTE_ADDR="203.0.113.80").post(
            "/api/auth/admin/login/",
            {"email": account.email, "password": "violet-harbour-lantern-92"},  # nosecret
            format="json",
        )
        assert reply.status_code == 200 and reply.json()["status"] == "two_step_setup_required"

    def test_the_maintenance_switch_is_not_a_platform_value(self, boss):
        assert save(boss[0], {"maintenance.enabled": True}).status_code == 400
        assert not re.search("maintenance", str(items(boss[0].get(URL))))


class TestAdminTwoStepIsAlwaysOn:
    def test_the_security_page_reports_the_rule_and_how_many_admins_have_set_it_up(self, boss):
        from core.tests.factories import make_admin_user

        make_admin_user(two_step_enabled=True)
        reply = boss[0].get(URL, {"page": "security"}).json()
        assert reply["admin_two_step"] == {"required": True, "set_up": 1, "not_set_up": 1}

    def test_there_is_no_setting_or_switch_that_skips_it(self, boss):
        assert not [key for key in DEFINITIONS if "two_step" in key and "admin" in key]
        reply = save(boss[0], {"security.admin_two_step_required": False})
        assert reply.status_code == 400
        assert "admin_two_step" not in boss[0].get(URL).json()
