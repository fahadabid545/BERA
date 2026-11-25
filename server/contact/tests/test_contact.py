import time

import pytest
from django.core import signing
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditEvent
from contact import form_token
from contact.models import ContactMessage
from contact.retention import purge_old_messages
from cvs.tests.test_ai_reading import set_setting
from emailing.models import OutgoingEmail
from platform_settings.branding import support_email

pytestmark = pytest.mark.django_db
URL = "/api/contact/"
FORM = "/api/contact/form/"


def old_token(seconds_ago):
    return signing.dumps({"opened_at": int(time.time()) - seconds_ago}, salt=form_token.SALT)


def body(**changes):
    values = {
        "name": "Fake Person",
        "email": "user@example.com",
        "message": "Hello, I have a question.",
        "website": "",
        "form_token": old_token(60),
    }
    return {**values, **changes}


def send(client=None, **changes):
    return (client or APIClient(REMOTE_ADDR="203.0.113.5")).post(
        URL, body(**changes), format="json"
    )


def support_mails():
    return [mail for mail in OutgoingEmail.objects.all() if mail.template == "contact_message"]


class TestASentMessage:
    def test_is_stored_and_the_sender_sees_a_thank_you(self):
        reply = send()
        assert (reply.status_code, reply.json()) == (
            200,
            {"message": "Thank you. Your message was sent."},
        )
        stored = ContactMessage.objects.get()
        assert (stored.name, stored.email, stored.message) == (
            "Fake Person",
            "user@example.com",
            "Hello, I have a question.",
        )

    def test_is_emailed_to_the_support_address(self):
        send()
        mail = support_mails()[0]
        assert mail.to_address == support_email()
        assert "Fake Person" in mail.text_body
        assert "user@example.com" in mail.text_body
        assert "Hello, I have a question." in mail.text_body

    def test_is_stored_encrypted(self):
        from django.db import connection

        send()
        with connection.cursor() as cursor:
            cursor.execute("select name, email, message from contact_contactmessage")
            row = cursor.fetchone()
        assert not any(
            word in str(value) for value in row for word in ("Fake", "example.com", "question")
        )

    def test_a_line_break_in_the_message_is_kept(self):
        send(message="First line\nSecond line")
        assert ContactMessage.objects.get().message == "First line\nSecond line"

    def test_nothing_about_the_sender_goes_to_the_logs_or_the_audit_log(self, project_log):
        send()
        assert "Fake Person" not in project_log.getvalue()
        assert "user@example.com" not in project_log.getvalue()
        assert not AuditEvent.objects.exists()


class TestMistakes:
    @pytest.mark.parametrize("field", ["name", "email", "message"])
    def test_a_missing_field_is_named(self, field):
        values = body()
        del values[field]
        reply = APIClient().post(URL, values, format="json")
        assert reply.status_code == 400
        assert field in reply.json()["error"]["fields"]
        assert not ContactMessage.objects.exists()

    def test_a_bad_email_is_refused(self):
        reply = send(email="not-an-email")
        assert (reply.status_code, "email" in reply.json()["error"]["fields"]) == (400, True)

    def test_a_blank_message_is_refused(self):
        assert send(message="   ").status_code == 400

    def test_a_name_with_a_line_break_is_refused(self):
        assert send(name="Fake\nPerson").status_code == 400

    def test_a_too_long_message_is_refused_using_the_setting(self):
        set_setting("contact.max_message_length", 10)
        reply = send(message="x" * 11)
        assert reply.status_code == 400
        assert "too long" in reply.json()["error"]["fields"]["message"]
        assert send(message="x" * 10).status_code == 200

    def test_a_too_long_name_is_refused_using_the_setting(self):
        set_setting("contact.max_name_length", 5)
        assert send(name="x" * 6).status_code == 400

    def test_an_unknown_field_is_refused(self):
        assert send(extra="x").status_code == 400


class TestSpam:
    def count(self, reason):
        return AuditEvent.objects.filter(
            kind="security.contact_spam_dropped", details__reason=reason
        ).count()

    def check_dropped(self, reply, reason):
        # The sender cannot tell: the same thank-you, but nothing is stored or emailed.
        assert (reply.status_code, reply.json()["message"]) == (
            200,
            "Thank you. Your message was sent.",
        )
        assert not ContactMessage.objects.exists()
        assert support_mails() == []
        assert self.count(reason) == 1

    def test_a_filled_hidden_field_is_dropped(self):
        self.check_dropped(send(website="http://spam.example.test"), "honeypot")

    def test_a_form_sent_too_fast_is_dropped(self):
        self.check_dropped(send(form_token=old_token(0)), "too_fast")

    def test_the_minimum_time_is_a_setting(self):
        set_setting("contact.min_fill_seconds", 30)
        self.check_dropped(send(form_token=old_token(10)), "too_fast")

    def test_an_expired_form_is_dropped(self):
        self.check_dropped(send(form_token=old_token(7200)), "expired")

    def test_a_missing_token_is_dropped(self):
        self.check_dropped(send(form_token=""), "invalid")

    def test_a_forged_token_is_dropped(self):
        self.check_dropped(send(form_token=old_token(60) + "x"), "invalid")

    def test_a_token_signed_for_something_else_is_dropped(self):
        other = signing.dumps({"opened_at": 1}, salt="something-else")
        self.check_dropped(send(form_token=other), "invalid")

    def test_nothing_the_sender_wrote_is_recorded_about_spam(self):
        send(website="http://spam.example.test", message="secret words")
        event = AuditEvent.objects.get(kind="security.contact_spam_dropped")
        assert event.details == {"reason": "honeypot"}


class TestTheLimit:
    def test_three_an_hour_per_address_then_a_clear_refusal(self):
        client = APIClient(REMOTE_ADDR="203.0.113.7")
        answers = [send(client).status_code for _ in range(4)]
        assert answers == [200, 200, 200, 429]
        assert ContactMessage.objects.count() == 3

    def test_another_address_is_not_affected(self):
        for _ in range(3):
            send(APIClient(REMOTE_ADDR="203.0.113.7"))
        assert send(APIClient(REMOTE_ADDR="203.0.113.8")).status_code == 200

    def test_dropped_spam_counts_too(self):
        client = APIClient(REMOTE_ADDR="203.0.113.7")
        for _ in range(3):
            send(client, website="x")
        assert send(client).status_code == 429

    def test_the_limit_is_the_platform_setting(self):
        set_setting("rate_limits.contact_per_hour", 1)
        client = APIClient(REMOTE_ADDR="203.0.113.7")
        assert [send(client).status_code for _ in range(2)] == [200, 429]

    def test_opening_the_form_is_not_counted(self):
        client = APIClient(REMOTE_ADDR="203.0.113.7")
        for _ in range(5):
            assert client.get(FORM).status_code == 200
        assert send(client).status_code == 200


class TestFailure:
    def test_when_the_email_cannot_be_stored_nothing_is_kept_and_the_sender_is_told(
        self, monkeypatch
    ):
        monkeypatch.setattr("contact.service.send_email", lambda *args, **kwargs: None)
        reply = send()
        assert reply.status_code == 503
        assert reply.json()["error"]["code"] == "contact_not_sent"
        assert "try again" in reply.json()["error"]["message"]
        assert not ContactMessage.objects.exists()

    def test_when_the_database_fails_the_message_is_plain(self, monkeypatch):
        from django.db import DatabaseError

        def fail(**_):
            raise DatabaseError("secret detail")

        monkeypatch.setattr("contact.service.ContactMessage.objects.create", fail)
        reply = send()
        assert reply.status_code == 503
        assert "secret detail" not in reply.content.decode()


class TestTheForm:
    def test_gives_a_signed_token_and_the_privacy_note(self):
        reply = APIClient().get(FORM)
        assert reply.status_code == 200
        assert reply["Cache-Control"] == "no-store"
        assert signing.loads(reply.json()["form_token"], salt=form_token.SALT)["opened_at"]

    def test_says_when_to_ask_for_a_fresh_token(self):
        set_setting("contact.form_max_age_seconds", 1000)
        assert APIClient().get(FORM).json()["refresh_after_seconds"] == 800

    def test_the_note_says_how_long_a_message_is_kept(self):
        note = APIClient().get(FORM).json()["privacy_note"]
        assert "90 days" in note
        set_setting("contact.retention_days", 30)
        assert "30 days" in APIClient().get(FORM).json()["privacy_note"]

    def test_the_note_is_a_platform_setting(self):
        set_setting("contact.privacy_note", "We only read it. Kept {days} days.")
        assert APIClient().get(FORM).json()["privacy_note"] == "We only read it. Kept 90 days."

    def test_a_note_that_does_not_say_how_long_is_refused(self):
        from platform_settings.definitions import SETTINGS

        definition = next(item for item in SETTINGS if item.key == "contact.privacy_note")
        assert not definition.is_valid("We keep it for a while.")
        assert definition.is_valid(definition.default)

    def test_a_token_from_the_form_works_after_the_minimum_time(self):
        set_setting("contact.min_fill_seconds", 1)
        token = APIClient().get(FORM).json()["form_token"]
        time.sleep(1.1)
        assert send(form_token=token).status_code == 200
        assert ContactMessage.objects.count() == 1


class TestRetention:
    def test_old_messages_are_deleted_and_recent_ones_stay(self):
        send()
        send()
        old = ContactMessage.objects.order_by("id").first()
        ContactMessage.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=91)
        )
        purge_old_messages()
        assert ContactMessage.objects.count() == 1

    def test_the_period_is_a_setting(self):
        send()
        ContactMessage.objects.update(created_at=timezone.now() - timezone.timedelta(days=10))
        set_setting("contact.retention_days", 30)
        purge_old_messages()
        assert ContactMessage.objects.count() == 1
        set_setting("contact.retention_days", 5)
        purge_old_messages()
        assert ContactMessage.objects.count() == 0

    def test_the_job_is_scheduled_daily(self):
        from django_q.models import Schedule

        job = Schedule.objects.get(func="contact.retention.purge_old_messages")
        assert job.schedule_type == "D"
