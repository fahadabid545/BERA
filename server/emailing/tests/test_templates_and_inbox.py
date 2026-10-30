import email
import email.policy
import re

import pytest
from django.core.management import call_command
from django.test import override_settings

from core.errors import AppError
from emailing.catalog import CATALOG
from emailing.links import build_link, validate_link
from emailing.rendering import render_email
from emailing.samples import sample_values
from emailing.service import send_email

TEMPLATES = list(CATALOG)
ADDRESS = "developer@example.test"

pytestmark = pytest.mark.django_db


@pytest.fixture
def inbox(settings, tmp_path):
    settings.EMAIL_BACKEND = "emailing.backends.DevInboxBackend"
    settings.EMAIL_FILE_PATH = tmp_path
    return tmp_path


def read(path):
    return email.message_from_bytes(path.read_bytes(), policy=email.policy.default)


def parts_of(message):
    text = message.get_body(("plain",)).get_content()
    html = message.get_body(("html",)).get_content()
    return text, html


def test_the_catalog_holds_exactly_the_agreed_emails():
    assert set(TEMPLATES) == {
        "verify_email",
        "reset_password",
        "team_invite",
        "password_changed",
        "email_changed",
        "new_sign_in",
        "usage_notice",
        "payment_problem",
    }


@pytest.mark.parametrize("template", TEMPLATES)
class TestEveryTemplate:
    def test_a_test_email_appears_in_the_development_inbox(self, inbox, template):
        send_email(template, ADDRESS, now=True, **sample_values(template))
        files = list(inbox.glob(f"*-{template}-*.eml"))
        assert len(files) == 1

    def test_it_has_the_bera_name_a_clear_subject_and_one_sender(self, inbox, template):
        send_email(template, ADDRESS, now=True, **sample_values(template))
        message = read(next(inbox.glob("*.eml")))
        text, html = parts_of(message)
        assert message["From"] == "Bera <bera@example.test>"
        assert message["To"] == ADDRESS
        assert len(message["Subject"]) > 10 and "\n" not in message["Subject"]
        assert "Bera" in message["Subject"] or "Bera" in html
        assert text.startswith("Bera") and ">Bera<" in html

    def test_it_has_a_plain_text_version_with_the_link(self, inbox, template):
        values = sample_values(template)
        send_email(template, ADDRESS, now=True, **values)
        text, _ = parts_of(read(next(inbox.glob("*.eml"))))
        assert CATALOG[template].button_label in text and values["link"] in text
        assert "<" not in text

    def test_it_has_exactly_one_main_button(self, inbox, template):
        values = sample_values(template)
        send_email(template, ADDRESS, now=True, **values)
        _, html = parts_of(read(next(inbox.glob("*.eml"))))
        links = re.findall(r"<a [^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a>", html)
        assert links == [(values["link"], CATALOG[template].button_label)]

    def test_its_link_points_to_the_website_and_holds_no_password(self, template):
        link = sample_values(template)["link"]
        assert link.startswith("http://localhost:3000/")
        assert "password" not in link.lower()

    def test_it_is_not_left_in_the_database_readably_or_at_all_after_sending(self, inbox, template):
        from emailing.models import OutgoingEmail

        send_email(template, ADDRESS, now=True, **sample_values(template))
        stored = OutgoingEmail.objects.get()
        assert stored.status == "sent"
        assert (stored.to_address, stored.subject, stored.text_body, stored.html_body) == ("",) * 4


def test_the_development_command_puts_one_of_each_in_the_inbox(inbox):
    call_command("send_test_emails")
    names = sorted(path.name.split("-", 2)[2].rsplit("-", 1)[0] for path in inbox.glob("*.eml"))
    assert names == sorted(TEMPLATES)


def test_the_development_command_refuses_outside_development(inbox):
    with override_settings(APP_ENV="production"):
        with pytest.raises(AppError) as caught:
            call_command("send_test_emails")
    assert caught.value.code == "development_only"
    assert not list(inbox.glob("*.eml"))


class TestRendering:
    def test_an_unknown_template_is_a_mistake_in_the_calling_code(self):
        with pytest.raises(ValueError, match="Unknown email template"):
            render_email("made_up", {})

    def test_a_missing_value_is_named(self):
        values = sample_values("verify_email")
        del values["expires_in_hours"]
        with pytest.raises(ValueError, match="expires_in_hours"):
            render_email("verify_email", values)

    def test_a_name_cannot_inject_html_but_stays_readable_in_the_text_version(self):
        values = {**sample_values("verify_email"), "name": "<script>alert(1)</script>"}
        _, text, html = render_email("verify_email", values)
        assert "<script>" not in html and "&lt;script&gt;" in html
        assert "<script>alert(1)</script>" in text

    def test_a_line_break_in_a_subject_value_cannot_inject_headers(self):
        values = {
            **sample_values("team_invite"),
            "inviter_name": "Jo\r\nBcc: attacker@example.test",
        }
        subject, _, _ = render_email("team_invite", values)
        assert "\n" not in subject and "\r" not in subject

    def test_the_subject_uses_the_values(self):
        subject, _, _ = render_email("team_invite", sample_values("team_invite"))
        assert subject == "Fake Owner invited you to Fake Test Company on Bera"


class TestLinks:
    def test_a_link_is_built_on_the_websites_address(self):
        assert build_link("/verify-email", token="abc") == (
            "http://localhost:3000/verify-email?token=abc"
        )

    @pytest.mark.parametrize("path", ["verify", "//evil.example/x", ""])
    def test_a_path_must_start_with_one_slash(self, path):
        with pytest.raises(ValueError):
            build_link(path)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.test/reset?token=abc",
            "http://localhost:3000.evil.example.test/reset",
            "http://localhost:3000@evil.example.test/reset",
            "https://localhost:3000/reset",
            "//evil.example.test/reset",
            "/reset",
        ],
    )
    def test_a_link_to_anywhere_else_is_refused(self, url):
        with pytest.raises(ValueError, match="Bera website"):
            validate_link(url)

    @pytest.mark.parametrize("name", ["password", "Password", "pwd", "pass", "secret", "passwd"])
    def test_a_link_never_carries_a_password(self, name):
        with pytest.raises(ValueError, match="password"):
            validate_link(f"http://localhost:3000/reset?{name}=hunter2")
        with pytest.raises(ValueError, match="password"):
            validate_link(f"http://localhost:3000/reset#{name}=hunter2")

    def test_a_very_long_link_is_refused(self):
        with pytest.raises(ValueError, match="too long"):
            validate_link("http://localhost:3000/reset?token=" + "a" * 3000)

    def test_the_renderer_refuses_a_bad_link_before_anything_is_stored(self):
        values = {**sample_values("reset_password"), "link": "https://evil.example.test/x"}
        with pytest.raises(ValueError):
            send_email("reset_password", ADDRESS, **values)
