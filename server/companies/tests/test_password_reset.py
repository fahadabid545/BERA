import logging
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from companies.models import CompanyUser
from core.tests.factories import make_company_user
from emailing import link_tokens
from emailing.models import LinkToken, OutgoingEmail
from emailing.service import deliver_email
from signin import service
from signin.models import Session

FORGOT = "/api/auth/company/forgot-password/"
RESET = "/api/auth/company/reset-password/"
LOGIN = "/api/auth/company/login/"
OLD = "violet-harbour-lantern-92"  # nosecret: fake test value
NEW = "copper-meadow-lantern-58"  # nosecret: fake test value
ANOTHER = "another-fresh-password-11"  # nosecret: fake test value
MESSAGE = "If an account exists, we sent a reset link"

pytestmark = pytest.mark.django_db


def person(email="owner@example.test", password=OLD, **fields):
    account = make_company_user(
        email=email, name="Fake Owner", **{"email_verified": True, **fields}
    )
    account.set_password(password)
    account.save()
    return account


def forgot(email, address="203.0.113.30"):
    return APIClient(REMOTE_ADDR=address).post(FORGOT, {"email": email}, format="json")


def reset(token, password=NEW, confirm=None, address="203.0.113.40", **extra):
    body = {
        "token": token,
        "password": password,
        "confirm_password": password if confirm is None else confirm,
        **extra,
    }
    return APIClient(REMOTE_ADDR=address).post(RESET, body, format="json")


def emails_sent():
    sent = []
    for email in OutgoingEmail.objects.filter(status="queued"):
        sent.append((email.template, email.to_address, email.text_body))
        deliver_email(str(email.id))
    return sent


def link_token_for(email="owner@example.test"):
    forgot(email)
    ((_, _, text),) = [item for item in emails_sent() if item[0] == "reset_password"]
    return re.search(r"/reset-password\?token=([\w-]+)", text).group(1)


def code_of(response):
    return response.json()["error"]["code"]


def log_in(email, password):
    return APIClient(REMOTE_ADDR="203.0.113.50").post(
        LOGIN, {"email": email, "password": password}, format="json"
    )


class TestAskingForTheLink:
    def test_an_account_gets_a_reset_email_and_the_answer_is_neutral(self):
        person()
        response = forgot("owner@example.test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": MESSAGE}
        ((template, to, text),) = emails_sent()
        assert (template, to) == ("reset_password", "owner@example.test")
        assert "Fake Owner" in text and "/reset-password?token=" in text and "1 hour" in text

    def test_the_answer_is_the_same_whether_or_not_there_is_an_account(self):
        person()
        known = forgot("owner@example.test", address="198.51.100.1")
        unknown = forgot("nobody@example.test", address="198.51.100.2")
        assert known.content == unknown.content and known.status_code == unknown.status_code == 200

    def test_nothing_is_sent_for_an_unknown_email(self):
        forgot("nobody@example.test")
        assert not OutgoingEmail.objects.exists() and not LinkToken.objects.exists()

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_blocked_and_removed_people_get_nothing(self, status):
        person(status=status, role="member")
        assert forgot("owner@example.test").json()["message"] == MESSAGE
        assert not OutgoingEmail.objects.exists()

    def test_someone_whose_email_is_not_verified_can_still_reset(self):
        person(email_verified=False)
        forgot("owner@example.test")
        assert [template for template, _, _ in emails_sent()] == ["reset_password"]

    @pytest.mark.parametrize("typed", ["OWNER@Example.test", " owner@example.test "])
    def test_in_any_spelling(self, typed):
        person()
        forgot(typed)
        assert len(emails_sent()) == 1

    def test_the_secret_is_random_single_purpose_stored_only_hashed_and_lasts_an_hour(self):
        account = person()
        token = link_token_for()
        stored = LinkToken.objects.get()
        assert token not in stored.token_hash and len(token) >= 40
        assert (stored.purpose, stored.subject_id) == ("reset_password", account.pk)
        assert timedelta(minutes=59) < stored.expires_at - timezone.now() <= timedelta(hours=1)

    def test_a_newer_link_cancels_the_older_one(self):
        person()
        first = link_token_for()
        second = link_token_for()
        assert code_of(reset(first)) == "link_used"
        assert reset(second).status_code == 200

    def test_it_is_limited_to_five_per_hour_per_email(self):
        person()
        statuses = [
            forgot("owner@example.test", address=f"198.51.100.{n}").status_code for n in range(7)
        ]
        assert statuses == [200] * 5 + [429, 429]
        assert OutgoingEmail.objects.filter(template="reset_password").count() == 5

    def test_the_limit_counts_every_spelling_and_unknown_emails_alike(self):
        for n, typed in enumerate(["a@example.test", "A@Example.test", " a@example.test "] * 2):
            forgot(typed, address=f"198.51.100.{n}")
        limited = forgot("a@example.test", address="198.51.100.99")
        assert limited.status_code == 429 and int(limited["Retry-After"]) > 0

    def test_another_email_is_not_affected(self):
        for n in range(6):
            forgot("a@example.test", address=f"198.51.100.{n}")
        assert forgot("b@example.test", address="198.51.100.99").status_code == 200

    @pytest.mark.parametrize(
        "body", [{}, {"email": "nonsense"}, {"email": 5}, {"email": "a@example.test", "x": 1}]
    )
    def test_a_bad_request_is_refused(self, body):
        assert APIClient().post(FORGOT, body, format="json").status_code == 400


class TestChoosingTheNewPassword:
    def test_the_new_password_replaces_the_old_one(self):
        person()
        token = link_token_for()
        response = reset(token)
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert log_in("owner@example.test", NEW).status_code == 200
        assert log_in("owner@example.test", OLD).status_code == 400

    def test_every_session_ends_and_nobody_is_signed_in_by_the_reset(self):
        account = person()
        sessions = [
            service.start_session(
                user_id=account.pk, role="owner", company_id=account.company_id, kind="company"
            )
            for _ in range(2)
        ]
        response = reset(link_token_for())
        assert not response.cookies
        assert not Session.objects.filter(status="active").exists()
        for issued in sessions:
            with pytest.raises(Exception) as caught:
                service.verify_access_token(issued.access_token, "company")
            assert caught.type.__name__ == "NotAuthenticated"

    def test_other_peoples_sessions_are_left_alone(self):
        person()
        other = person(email="other@example.test")
        theirs = service.start_session(
            user_id=other.pk, role="owner", company_id=other.company_id, kind="company"
        )
        reset(link_token_for())
        assert service.verify_access_token(theirs.access_token, "company")

    def test_a_confirmation_email_follows(self):
        person()
        token = link_token_for()
        mail.outbox.clear()
        reset(token)
        ((template, to, text),) = emails_sent()
        assert (template, to) == ("password_changed", "owner@example.test")
        assert "Fake Owner" in text and "UTC" in text and "/forgot-password" in text
        assert OLD not in text and NEW not in text

    def test_the_email_stays_unverified_if_it_was(self):
        person(email_verified=False)
        reset(link_token_for())
        assert CompanyUser.objects.get().email_verified is False


class TestTheLink:
    def test_it_works_once(self):
        person()
        token = link_token_for()
        assert reset(token).status_code == 200
        again = reset(token, password=ANOTHER)
        assert code_of(again) == "link_used"
        assert again.json()["error"]["message"] == "This link has already been used."
        assert log_in("owner@example.test", NEW).status_code == 200

    def test_it_expires_after_an_hour(self):
        person()
        token = link_token_for()
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = reset(token)
        assert code_of(response) == "link_expired"
        assert response.json()["error"]["message"] == "This link has expired."
        assert log_in("owner@example.test", OLD).status_code == 200

    def test_it_still_works_just_before_the_hour_is_up(self, monkeypatch):
        person()
        token = link_token_for()
        created = LinkToken.objects.get().created_at
        monkeypatch.setattr(link_tokens.timezone, "now", lambda: created + timedelta(minutes=59))
        assert reset(token).status_code == 200

    def test_a_made_up_link_is_not_valid(self):
        assert code_of(reset("made-up-" + "x" * 40)) == "link_invalid"

    def test_a_verification_link_cannot_reset_a_password(self):
        account = person()
        token = link_tokens.issue_link_token("verify_email", account.pk, 24)
        assert code_of(reset(token)) == "link_invalid"
        assert LinkToken.objects.get().used_at is None
        assert log_in("owner@example.test", OLD).status_code == 200

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_a_link_for_a_blocked_or_removed_account_is_not_valid_and_not_spent(self, status):
        account = person(role="member")
        token = link_tokens.issue_link_token("reset_password", account.pk, 1)
        CompanyUser.objects.filter(pk=account.pk).update(status=status)
        assert code_of(reset(token)) == "link_invalid"
        assert LinkToken.objects.get().used_at is None

    def test_after_a_used_or_expired_link_a_new_one_can_be_requested(self):
        person()
        token = link_token_for()
        reset(token)
        assert code_of(reset(token)) == "link_used"
        fresh = link_token_for()
        assert reset(fresh, password=ANOTHER).status_code == 200


class TestRefusedPasswords:
    def test_the_new_password_cannot_be_the_old_one(self):
        person()
        token = link_token_for()
        response = reset(token, password=OLD)
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["password"] == (
            "Your new password must be different from your old one."
        )

    def test_a_refused_password_does_not_use_up_the_link(self):
        person()
        token = link_token_for()
        reset(token, password=OLD)
        assert LinkToken.objects.get().used_at is None
        assert reset(token).status_code == 200  # another try with the same link works

    def test_a_refused_password_changes_nothing(self):
        account = person()
        service.start_session(
            user_id=account.pk, role="owner", company_id=account.company_id, kind="company"
        )
        reset(link_token_for(), password=OLD)
        assert Session.objects.filter(status="active").count() == 1
        assert not [t for t, _, _ in emails_sent() if t == "password_changed"]

    def test_a_weak_password_is_refused_with_all_the_reasons(self):
        person()
        token = link_token_for()
        response = reset(token, password="password")
        message = response.json()["error"]["fields"]["password"]
        assert "at least 12 characters" in message and "too common" in message
        assert LinkToken.objects.get().used_at is None

    def test_the_two_entries_must_match(self):
        person()
        token = link_token_for()
        response = reset(token, confirm=NEW + "x")
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["confirm_password"] == (
            "The passwords do not match."
        )
        assert LinkToken.objects.get().used_at is None
        assert log_in("owner@example.test", OLD).status_code == 200

    @pytest.mark.parametrize("missing", ["token", "password", "confirm_password"])
    def test_every_field_is_required(self, missing):
        body = {"token": "x" * 43, "password": NEW, "confirm_password": NEW}
        del body[missing]
        response = APIClient().post(RESET, body, format="json")
        assert response.status_code == 400 and missing in response.json()["error"]["fields"]

    def test_other_fields_are_refused(self):
        person()
        assert reset(link_token_for(), email="someone.else@example.test").status_code == 400

    @pytest.mark.parametrize("value", [123456789012, ["a"], None])
    def test_a_password_that_is_not_text_is_refused(self, value):
        body = {"token": "x" * 43, "password": value, "confirm_password": value}
        assert APIClient().post(RESET, body, format="json").status_code == 400

    def test_passwords_are_never_in_the_answer_or_the_log(self, caplog):
        person()
        token = link_token_for()
        with caplog.at_level(logging.DEBUG):
            bad = reset(token, password=OLD)
            good = reset(token)
        text = bad.content.decode() + good.content.decode() + caplog.text
        assert OLD not in text and NEW not in text and token not in caplog.text
        assert "owner@example.test" not in caplog.text
