import logging
import smtplib
from datetime import timedelta

import pytest
from django.db import DatabaseError, connection
from django.utils import timezone
from django_q.models import Schedule

from emailing import service
from emailing.models import BouncedAddress, OutgoingEmail
from emailing.samples import sample_values
from emailing.service import deliver_email, record_bounce, send_email
from emailing.tests.flaky_backend import FlakyBackend

ADDRESS = "Jo.Reader@Example.test"
WAITS = [60, 300, 1800]

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider(settings):
    settings.EMAIL_BACKEND = "emailing.tests.flaky_backend.FlakyBackend"
    FlakyBackend.reset()
    return FlakyBackend


def queue(address=ADDRESS):
    return send_email("verify_email", address, **sample_values("verify_email"))


def run(email):
    deliver_email(str(email.id))
    email.refresh_from_db()
    return email


class TestSending:
    def test_the_email_is_stored_unreadably_and_queued_after_the_action_commits(
        self, provider, django_capture_on_commit_callbacks, monkeypatch
    ):
        queued = []
        monkeypatch.setattr(service, "async_task", lambda job, email_id: queued.append(email_id))
        with django_capture_on_commit_callbacks(execute=True):
            email = queue()
            assert queued == []  # nothing before the surrounding action is saved
        assert queued == [str(email.id)]
        with connection.cursor() as cursor:
            cursor.execute("SELECT t::text FROM emailing_outgoingemail t")
            row = cursor.fetchone()[0]
        assert "example.test" not in row and "token" not in row and "Fake Person" not in row

    def test_an_action_that_is_rolled_back_sends_nothing(
        self, provider, django_capture_on_commit_callbacks, monkeypatch
    ):
        queued = []
        monkeypatch.setattr(service, "async_task", lambda job, email_id: queued.append(email_id))
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            queue()
        callbacks.clear()  # a rollback discards them; nothing may run
        assert queued == []

    def test_a_delivery_sends_one_message_to_the_address_and_wipes_the_record(self, provider):
        email = run(queue())
        assert email.status == "sent" and email.attempts == 1 and email.finished_at
        (message,) = provider.delivered
        assert message.to == [ADDRESS] and message.from_email == "Bera <bera@example.test>"
        assert message.alternatives[0][1] == "text/html"
        assert email.to_address == "" and email.text_body == ""

    def test_a_repeated_job_sends_nothing_twice(self, provider):
        email = run(queue())
        run(email)
        assert len(provider.delivered) == 1

    def test_sending_immediately_delivers_before_returning(self, provider):
        email = send_email("verify_email", ADDRESS, now=True, **sample_values("verify_email"))
        assert len(provider.delivered) == 1
        assert email.status == "sent"  # the returned email shows the outcome


class TestFailures:
    def test_a_provider_failure_never_reaches_the_users_action(self, provider):
        provider.reset(failures=99)
        send_email("verify_email", ADDRESS, now=True, **sample_values("verify_email"))

    def test_a_failure_is_retried_after_the_configured_waits(self, provider):
        provider.reset(failures=2)
        email = queue()
        for expected_attempts, wait in ((1, WAITS[0]), (2, WAITS[1])):
            before = timezone.now()
            run(email)
            assert email.status == "queued" and email.attempts == expected_attempts
            assert email.last_error == "SMTPServerDisconnected"
            retry = Schedule.objects.filter(name__endswith=f"-{expected_attempts}").get()
            assert retry.func == service.DELIVER_JOB and str(email.id) in retry.args
            assert (
                timedelta(seconds=wait - 5) < retry.next_run - before < timedelta(seconds=wait + 5)
            )
        run(email)
        assert email.status == "sent" and len(provider.delivered) == 1
        assert provider.attempts == 3

    def test_after_three_retries_it_gives_up_and_logs(self, provider, caplog):
        provider.reset(failures=99)
        email = queue()
        with caplog.at_level(logging.WARNING):
            for _ in range(4):
                run(email)
        assert email.status == "failed" and email.attempts == 4
        assert provider.attempts == 4  # the first try and three retries
        assert Schedule.objects.count() == 3  # no fourth retry
        assert "was not sent after 4 attempts" in caplog.text
        assert (email.to_address, email.text_body, email.html_body) == ("", "", "")

    def test_nothing_is_retried_after_giving_up(self, provider):
        provider.reset(failures=99)
        email = queue()
        for _ in range(4):
            run(email)
        run(email)
        assert provider.attempts == 4

    @pytest.mark.parametrize(
        "error",
        [
            smtplib.SMTPServerDisconnected,
            TimeoutError,
            ConnectionRefusedError,
            smtplib.SMTPException,
        ],
    )
    def test_every_kind_of_provider_or_network_failure_is_retried(self, provider, error):
        provider.reset(failures=1, error=error)
        email = run(queue())
        assert email.status == "queued" and email.attempts == 1

    def test_the_log_never_contains_the_address_or_the_message(self, provider, caplog):
        provider.reset(failures=99)
        email = queue()
        with caplog.at_level(logging.DEBUG):
            for _ in range(4):
                run(email)
        assert "example.test" not in caplog.text.lower()
        assert "Fake Person" not in caplog.text and "sample-token" not in caplog.text

    def test_a_down_queue_does_not_break_the_users_action(
        self, provider, django_capture_on_commit_callbacks, monkeypatch, caplog
    ):
        def broken(*args, **kwargs):
            raise ConnectionError("queue is down")

        monkeypatch.setattr(service, "async_task", broken)
        with django_capture_on_commit_callbacks(execute=True):
            email = queue()
        assert email.status == "queued"  # still stored, ready for a later sweep
        assert "Could not queue email" in caplog.text

    def test_a_database_failure_while_storing_does_not_break_the_users_action(
        self, provider, monkeypatch, caplog
    ):
        def broken(**fields):
            raise DatabaseError("disk full")

        monkeypatch.setattr(OutgoingEmail.objects, "create", broken)
        assert queue() is None
        assert "Could not store a verify_email email" in caplog.text


class TestBounces:
    def refuse(self, provider):
        provider.reset(
            failures=1, error=lambda message: smtplib.SMTPRecipientsRefused({ADDRESS: (550, b"no")})
        )

    def test_a_refused_address_is_recorded_and_not_retried(self, provider):
        self.refuse(provider)
        email = run(queue())
        assert email.status == "failed" and email.last_error == "SMTPRecipientsRefused"
        assert BouncedAddress.objects.filter(address_lookup=ADDRESS).count() == 1
        assert not Schedule.objects.exists()

    def test_later_emails_to_a_bounced_address_are_not_sent_in_any_spelling(self, provider):
        record_bounce("jo.reader@example.test", BouncedAddress.Kind.HARD_BOUNCE)
        email = run(queue(" JO.READER@example.test "))
        assert email.status == "suppressed" and provider.attempts == 0

    def test_an_email_already_waiting_is_stopped_when_its_address_bounces(self, provider):
        email = queue()
        record_bounce(ADDRESS, BouncedAddress.Kind.COMPLAINT)
        assert run(email).status == "suppressed" and provider.attempts == 0

    def test_recording_the_same_bounce_twice_keeps_one_record(self):
        record_bounce(ADDRESS, BouncedAddress.Kind.HARD_BOUNCE)
        record_bounce(ADDRESS.lower(), BouncedAddress.Kind.HARD_BOUNCE)
        assert BouncedAddress.objects.count() == 1

    def test_the_address_is_not_stored_readably(self):
        record_bounce(ADDRESS, BouncedAddress.Kind.HARD_BOUNCE)
        with connection.cursor() as cursor:
            cursor.execute("SELECT t::text FROM emailing_bouncedaddress t")
            assert "example.test" not in cursor.fetchone()[0].lower()
        assert BouncedAddress.objects.get().address == ADDRESS

    def test_other_addresses_are_unaffected(self, provider):
        record_bounce(ADDRESS, BouncedAddress.Kind.HARD_BOUNCE)
        assert run(queue("someone.else@example.test")).status == "sent"
