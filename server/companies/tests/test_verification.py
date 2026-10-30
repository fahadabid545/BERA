import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from companies.models import CompanyUser
from core.tests.factories import make_admin_user, make_company_user
from emailing import link_tokens
from emailing.models import LinkToken, OutgoingEmail
from emailing.service import deliver_email
from signin import service
from signin.cookies import refresh_cookie_name
from signin.models import Session

VERIFY = "/api/auth/company/verify-email/"
RESEND = "/api/auth/company/verify-email/resend/"
SIGN_UP = "/api/auth/company/signup/"
STRONG = "violet-harbour-lantern-92"  # nosecret: fake test value
RESEND_MESSAGE = "If this email still needs verifying, we have sent a new link."

pytestmark = pytest.mark.django_db


def sign_up(email="owner@example.test", address="203.0.113.10"):
    body = {
        "company_name": "Fake Ltd",
        "name": "Fake Owner",
        "email": email,
        "password": STRONG,
        "country": "DE",
        "accept_terms": True,
    }
    assert APIClient(REMOTE_ADDR=address).post(SIGN_UP, body, format="json").status_code == 200


def tokens_sent():
    """The tokens inside the verification emails queued so far (and sends them)."""
    found = []
    for email in OutgoingEmail.objects.filter(status="queued"):
        found += re.findall(r"token=([\w-]+)", email.text_body)
        deliver_email(str(email.id))
    return found


def verify(token, client=None, **extra):
    client = client or APIClient(REMOTE_ADDR="203.0.113.20")
    return client.post(VERIFY, {"token": token, **extra}, format="json")


def resend(email, address="203.0.113.30"):
    return APIClient(REMOTE_ADDR=address).post(RESEND, {"email": email}, format="json")


def error_code(response):
    return response.json()["error"]["code"]


@pytest.fixture
def fresh_owner():
    sign_up()
    (token,) = tokens_sent()
    return CompanyUser.objects.get(), token


class TestVerifying:
    def test_the_link_from_sign_up_verifies_the_owner(self, fresh_owner):
        owner, token = fresh_owner
        assert owner.email_verified is False
        response = verify(token)
        assert response.status_code == 200 and response.json() == {"status": "verified"}
        owner.refresh_from_db()
        assert owner.email_verified is True

    def test_the_link_works_once(self, fresh_owner):
        _, token = fresh_owner
        assert verify(token).status_code == 200
        again = verify(token)
        assert again.status_code == 400 and error_code(again) == "link_used"
        assert again.json()["error"]["message"] == "This link has already been used."

    def test_the_stored_secret_is_only_a_hash(self, fresh_owner):
        _, token = fresh_owner
        assert token not in LinkToken.objects.get().token_hash

    def test_the_link_expires_after_24_hours(self, fresh_owner, monkeypatch):
        owner, token = fresh_owner
        created = LinkToken.objects.get().created_at
        monkeypatch.setattr(
            link_tokens.timezone, "now", lambda: created + timedelta(hours=24, minutes=1)
        )
        response = verify(token)
        assert error_code(response) == "link_expired"
        assert response.json()["error"]["message"] == "This link has expired."
        owner.refresh_from_db()
        assert owner.email_verified is False

    def test_it_still_works_just_before_24_hours(self, fresh_owner, monkeypatch):
        owner, token = fresh_owner
        created = LinkToken.objects.get().created_at
        monkeypatch.setattr(
            link_tokens.timezone, "now", lambda: created + timedelta(hours=23, minutes=59)
        )
        assert verify(token).status_code == 200

    def test_an_expired_link_is_not_used_up(self, fresh_owner):
        _, token = fresh_owner
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        verify(token)
        assert LinkToken.objects.get().used_at is None

    def test_a_made_up_link_is_not_valid(self):
        response = verify("made-up-" + "x" * 40)
        assert response.status_code == 400 and error_code(response) == "link_invalid"

    def test_a_link_meant_for_another_purpose_does_not_verify_and_is_not_spent(self):
        person = make_company_user(role="member")
        token = link_tokens.issue_link_token("reset_password", person.pk, 1)
        assert error_code(verify(token)) == "link_invalid"
        assert LinkToken.objects.get().used_at is None
        person.refresh_from_db()
        assert person.email_verified is False

    def test_a_link_for_a_removed_account_is_not_valid_and_is_not_spent(self):
        person = make_company_user(role="member", status="removed")
        token = link_tokens.issue_link_token("verify_email", person.pk, 24)
        assert error_code(verify(token)) == "link_invalid"
        assert LinkToken.objects.get().used_at is None

    def test_verifying_twice_with_two_different_links_is_harmless(self, fresh_owner):
        owner, first = fresh_owner
        second = link_tokens.issue_link_token("verify_email", owner.pk, 24)
        assert verify(first).status_code == 200 and verify(second).status_code == 200

    @pytest.mark.parametrize(
        "body", [{}, {"token": ""}, {"token": 12345}, {"token": None}, {"token": ["a"]}]
    )
    def test_the_token_is_required_text(self, body):
        response = APIClient().post(VERIFY, body, format="json")
        assert response.status_code == 400 and "token" in response.json()["error"]["fields"]

    def test_other_fields_are_refused_so_nobody_can_choose_what_to_change(self, fresh_owner):
        _, token = fresh_owner
        response = verify(token, email_verified=False, user_id=99)
        assert response.status_code == 400
        assert CompanyUser.objects.get().email_verified is False

    def test_only_the_post_method_is_allowed(self, fresh_owner):
        _, token = fresh_owner
        assert APIClient().get(f"{VERIFY}?token={token}").status_code == 405
        assert CompanyUser.objects.get().email_verified is False


class TestWhileSignedInAsSomeoneElse:
    @pytest.fixture
    def other(self):
        person = make_company_user(role="member", email="someone.else@example.test")
        issued = service.start_session(
            user_id=person.pk, role="member", company_id=person.company_id, kind="company"
        )
        return person, issued

    def test_the_link_verifies_its_own_person_and_nobody_else(self, fresh_owner, other):
        owner, token = fresh_owner
        person, issued = other
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert verify(token, client=client).status_code == 200
        owner.refresh_from_db()
        person.refresh_from_db()
        assert owner.email_verified is True and person.email_verified is False

    def test_the_signed_in_session_is_neither_changed_nor_replaced(self, fresh_owner, other):
        _, token = fresh_owner
        person, issued = other
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        client.cookies[refresh_cookie_name("company")] = issued.refresh_token
        sessions_before = list(Session.objects.values_list("id", "status", "refresh_token_hash"))
        response = verify(token, client=client)
        assert not response.cookies  # nobody is signed in or out by clicking a link
        assert (
            list(Session.objects.values_list("id", "status", "refresh_token_hash"))
            == sessions_before
        )

    def test_a_signed_in_admin_changes_nothing_either(self, fresh_owner):
        _, token = fresh_owner
        admin = make_admin_user()
        issued = service.start_session(
            user_id=admin.pk, role="super", company_id=None, kind="admin"
        )
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert verify(token, client=client).status_code == 200
        assert Session.objects.get().status == "active"

    def test_the_answer_names_no_one(self, fresh_owner, other):
        _, token = fresh_owner
        assert "example.test" not in verify(token).content.decode()


class TestResending:
    def unverified(self):
        sign_up()
        tokens_sent()
        mail.outbox.clear()
        return CompanyUser.objects.get()

    def test_an_unverified_owner_gets_a_new_working_link(self):
        owner = self.unverified()
        response = resend("owner@example.test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": RESEND_MESSAGE}
        (token,) = tokens_sent()
        assert [m.to for m in mail.outbox] == [["owner@example.test"]]
        assert verify(token).status_code == 200
        owner.refresh_from_db()
        assert owner.email_verified is True

    def test_the_older_link_stops_working(self):
        sign_up()
        (old,) = tokens_sent()
        resend("owner@example.test")
        (new,) = tokens_sent()
        assert error_code(verify(old)) == "link_used"
        assert verify(new).status_code == 200

    def test_an_expired_link_can_be_replaced(self):
        sign_up()
        (old,) = tokens_sent()
        LinkToken.objects.update(expires_at=timezone.now() - timedelta(hours=1))
        assert error_code(verify(old)) == "link_expired"
        resend("owner@example.test")
        (new,) = tokens_sent()
        assert verify(new).status_code == 200

    @pytest.mark.parametrize("typed", ["OWNER@example.test", " owner@example.test "])
    def test_in_any_spelling(self, typed):
        self.unverified()
        resend(typed)
        assert len(tokens_sent()) == 1

    def test_the_answer_is_the_same_whether_or_not_the_email_exists_or_needs_it(self):
        self.unverified()
        verified = make_company_user(
            role="member", email="verified@example.test", email_verified=True
        )
        answers = {
            resend(email, address=f"198.51.100.{n}").content
            for n, email in enumerate(
                ["owner@example.test", "nobody@example.test", verified.email], start=1
            )
        }
        assert len(answers) == 1

    def test_someone_already_verified_gets_nothing(self):
        make_company_user(role="member", email="done@example.test", email_verified=True)
        assert resend("done@example.test").status_code == 200
        assert not OutgoingEmail.objects.exists() and not LinkToken.objects.exists()

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_blocked_and_removed_people_get_nothing(self, status):
        make_company_user(role="member", email="quiet@example.test", status=status)
        assert resend("quiet@example.test").status_code == 200
        assert not OutgoingEmail.objects.exists() and not LinkToken.objects.exists()

    def test_an_unknown_email_gets_nothing(self):
        assert resend("nobody@example.test").status_code == 200
        assert not OutgoingEmail.objects.exists()

    def test_it_is_limited_to_three_per_hour_per_email(self):
        self.unverified()
        statuses = [
            resend("owner@example.test", address=f"198.51.100.{n}").status_code for n in range(5)
        ]
        assert statuses == [200, 200, 200, 429, 429]

    def test_the_limit_counts_the_same_email_in_any_spelling_and_for_unknown_emails(self):
        for n, typed in enumerate(["a@example.test", "A@Example.test", " a@example.test "]):
            resend(typed, address=f"198.51.100.{n}")
        limited = resend("a@example.test", address="198.51.100.9")
        assert limited.status_code == 429 and int(limited["Retry-After"]) > 0

    def test_another_email_is_not_affected(self):
        for n in range(4):
            resend("a@example.test", address=f"198.51.100.{n}")
        assert resend("b@example.test", address="198.51.100.9").status_code == 200

    def test_only_three_emails_go_out_even_if_more_are_asked_for(self):
        self.unverified()
        for n in range(6):
            resend("owner@example.test", address=f"198.51.100.{n}")
        assert OutgoingEmail.objects.filter(template="verify_email", status="queued").count() == 3

    @pytest.mark.parametrize(
        "body", [{}, {"email": "nonsense"}, {"email": 5}, {"email": "a@example.test", "x": 1}]
    )
    def test_a_bad_request_is_refused(self, body):
        response = APIClient().post(RESEND, body, format="json")
        assert response.status_code == 400

    def test_the_limit_is_the_platform_setting(self):
        from core import rate_limits

        assert (
            rate_limits.RESEND_VERIFICATION.setting_key
            == "rate_limits.verification_resend_per_hour"
        )
