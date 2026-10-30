import logging
from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from companies.models import CompanyUser
from core import rate_limits, request_context
from core.tests.factories import make_company, make_company_user
from platform_settings.models import PlatformSetting
from signin import login, service
from signin.cookies import CSRF_COOKIE, access_cookie_name, refresh_cookie_name
from signin.models import Session

URL = "/api/auth/company/login/"
PASSWORD = "violet-harbour-lantern-92"  # nosecret: fake test value
GENERIC = "Email or password is incorrect."

pytestmark = pytest.mark.django_db


def person(email="owner@example.test", password=PASSWORD, **fields):
    fields = {"email_verified": True, "role": "owner", **fields}
    company = fields.pop("company", None) or make_company()
    account = make_company_user(company, email=email, **fields)
    account.set_password(password)
    account.save()
    return account


def log_in(email="owner@example.test", password=PASSWORD, address="203.0.113.10", **extra):
    body = {"email": email, "password": password, **extra}
    return APIClient(REMOTE_ADDR=address).post(URL, body, format="json")


def code_of(response):
    return response.json()["error"]["code"]


class TestSigningIn:
    def test_the_right_email_and_password_sign_the_person_in(self):
        account = person()
        response = log_in()
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        session = Session.objects.get()
        assert (session.user_id, session.kind, session.company_id) == (
            account.pk,
            "company",
            account.company_id,
        )

    def test_the_tokens_travel_only_in_protected_cookies(self):
        person()
        response = log_in()
        for name in (access_cookie_name("company"), refresh_cookie_name("company")):
            cookie = response.cookies[name]
            assert cookie["httponly"] and cookie["samesite"] == "Strict"
        assert CSRF_COOKIE in response.cookies
        token = response.cookies[access_cookie_name("company")].value
        assert token not in response.content.decode()

    def test_the_cookie_works_for_the_session_that_was_started(self):
        account = person()
        response = log_in()
        user = service.verify_access_token(
            response.cookies[access_cookie_name("company")].value, "company"
        )
        assert (user.user_id, user.role, user.company_id) == (
            account.pk,
            "owner",
            account.company_id,
        )

    def test_a_member_gets_the_member_role(self):
        person(role="member", email="member@example.test")
        token = log_in("member@example.test").cookies[access_cookie_name("company")].value
        assert service.verify_access_token(token, "company").role == "member"

    @pytest.mark.parametrize("typed", ["OWNER@Example.test", "  owner@example.test "])
    def test_the_email_may_be_typed_in_any_spelling(self, typed):
        person()
        assert log_in(typed).status_code == 200

    def test_the_password_is_exact_including_spaces_and_capitals(self):
        person()
        assert code_of(log_in(password=PASSWORD.upper())) == "invalid_credentials"
        assert code_of(log_in(password=PASSWORD + " ")) == "invalid_credentials"

    def test_the_actor_is_noted_for_the_log(self, monkeypatch):
        account = person()
        noted = []
        monkeypatch.setattr(request_context, "bind_actor", lambda *ids: noted.append(ids))
        log_in()
        assert noted == [(account.pk, account.company_id)]


class TestSeveralDevices:
    def test_a_second_device_gets_its_own_session_and_the_first_keeps_working(self):
        person()
        first, second = log_in(), log_in()
        assert Session.objects.filter(status="active").count() == 2
        tokens = [r.cookies[access_cookie_name("company")].value for r in (first, second)]
        assert all(service.verify_access_token(t, "company") for t in tokens)

    def test_ending_one_session_leaves_the_other(self):
        person()
        first, second = log_in(), log_in()
        first_user = service.verify_access_token(
            first.cookies[access_cookie_name("company")].value, "company"
        )
        service.revoke_session(first_user.session_id, "logout")
        assert service.verify_access_token(
            second.cookies[access_cookie_name("company")].value, "company"
        )


class TestWrongDetails:
    def test_a_wrong_password_and_an_unknown_email_look_exactly_alike(self):
        person()
        wrong_password = log_in(password="not-the-password-1")
        unknown_email = log_in("nobody@example.test", "not-the-password-1")
        assert wrong_password.status_code == unknown_email.status_code == 400
        assert wrong_password.content == unknown_email.content
        assert wrong_password.json()["error"]["message"] == GENERIC

    def test_nothing_is_signed_in(self):
        person()
        log_in(password="not-the-password-1")
        assert not Session.objects.exists()

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_a_blocked_or_removed_person_cannot_sign_in_and_is_told_no_more(self, status):
        person(status=status, role="member")
        wrong = log_in("nobody@example.test", "not-the-password-1")
        response = log_in()
        assert response.status_code == 400 and response.content == wrong.content
        assert not Session.objects.exists()

    def test_a_person_without_a_password_yet_cannot_sign_in(self):
        account = person()
        account.set_unusable_password()
        account.save()
        assert code_of(log_in(password="anything-at-all")) == "invalid_credentials"

    def test_a_password_that_is_far_too_long_is_just_wrong(self):
        person()
        assert code_of(log_in(password="a" * 3000)) == "invalid_credentials"

    def test_the_right_password_of_someone_else_does_not_work(self):
        person()
        person(email="other@example.test", password="completely-other-pass-77")
        assert code_of(log_in("owner@example.test", "completely-other-pass-77")) == (
            "invalid_credentials"
        )


class TestWhatTheRightPasswordLearnsAboutTheAccount:
    def test_an_unverified_email(self):
        person(email_verified=False)
        response = log_in()
        assert response.status_code == 403 and code_of(response) == "email_not_verified"
        assert response.json()["error"]["message"] == "Please verify your email"
        assert not Session.objects.exists()

    def test_a_suspended_company(self):
        person(company=make_company(status="suspended"))
        response = log_in()
        assert response.status_code == 403 and code_of(response) == "company_suspended"
        assert response.json()["error"]["message"] == (
            "Your company account is suspended. Please contact support."
        )
        assert not Session.objects.exists()

    def test_suspension_comes_before_the_unverified_notice(self):
        person(company=make_company(status="suspended"), email_verified=False)
        assert code_of(log_in()) == "company_suspended"

    def test_a_wrong_password_never_reveals_either_state(self):
        person(email_verified=False, email="unverified@example.test")
        person(company=make_company(status="suspended"), email="suspended@example.test")
        for email in ("unverified@example.test", "suspended@example.test"):
            response = log_in(email, "not-the-password-1")
            assert response.json()["error"]["message"] == GENERIC

    def test_these_notices_do_not_count_as_failed_attempts(self):
        person(email_verified=False)
        for _ in range(8):
            assert code_of(log_in()) == "email_not_verified"


class TestThePause:
    def fail(self, times, email="owner@example.test"):
        return [log_in(email, "not-the-password-1") for _ in range(times)]

    def test_five_failed_attempts_pause_the_account_for_15_minutes(self):
        person()
        responses = self.fail(5)
        assert [r.status_code for r in responses] == [400, 400, 400, 400, 429]
        assert responses[-1].json()["error"]["message"] == (
            "Too many attempts. Try again in 15 minutes."
        )
        assert responses[-1]["Retry-After"] == "900"

    def test_while_paused_even_the_right_password_is_refused(self):
        person()
        self.fail(5)
        response = log_in()
        assert response.status_code == 429 and not Session.objects.exists()

    def test_an_unknown_email_is_paused_in_the_same_way(self):
        statuses = [r.status_code for r in self.fail(6, "nobody@example.test")]
        assert statuses == [400, 400, 400, 400, 429, 429]

    def test_another_account_is_not_paused(self):
        person()
        person(email="other@example.test")
        self.fail(5)
        assert log_in("other@example.test").status_code == 200

    def test_the_pause_is_by_account_not_by_address(self):
        person()
        for number in range(5):
            log_in(password="not-the-password-1", address=f"198.51.100.{number}")
        assert log_in(address="198.51.100.99").status_code == 429

    def test_a_blocked_persons_guesses_count_too(self):
        person(status="blocked", role="member")
        assert [r.status_code for r in self.fail(5)][-1] == 429

    def test_a_successful_sign_in_clears_the_count(self):
        person()
        self.fail(4)
        assert log_in().status_code == 200
        assert [r.status_code for r in self.fail(4)] == [400] * 4

    def test_the_pause_ends_after_15_minutes(self, monkeypatch):
        person()
        start = datetime(2030, 1, 1, tzinfo=UTC)
        monkeypatch.setattr(rate_limits, "now", lambda: start)
        self.fail(5)
        monkeypatch.setattr(rate_limits, "now", lambda: start + timedelta(minutes=14))
        assert log_in().status_code == 429
        monkeypatch.setattr(rate_limits, "now", lambda: start + timedelta(minutes=16))
        assert log_in().status_code == 200

    def test_failures_more_than_15_minutes_apart_do_not_add_up(self, monkeypatch):
        person()
        start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
        monkeypatch.setattr(rate_limits, "now", lambda: start)
        self.fail(4)
        monkeypatch.setattr(rate_limits, "now", lambda: start + timedelta(minutes=16))
        assert self.fail(1)[0].status_code == 400

    def test_the_numbers_are_platform_settings(self):
        PlatformSetting.objects.create(key="signin.max_failed_attempts", value=2)
        PlatformSetting.objects.create(key="signin.lockout_minutes", value=30)
        person()
        responses = self.fail(2)
        assert responses[-1].status_code == 429 and responses[-1]["Retry-After"] == "1800"


class TestTheAddressLimit:
    def test_the_eleventh_attempt_in_a_minute_from_one_address_is_slowed_down(self):
        statuses = [log_in(f"nobody{n}@example.test", "x").status_code for n in range(11)]
        assert statuses[:10] == [400] * 10 and statuses[10] == 429

    def test_it_is_the_existing_login_limit(self):
        from core.throttles import LoginThrottle

        assert LoginThrottle.rule.setting_key == "rate_limits.login_per_minute"


class TestSecrecy:
    def test_the_login_time_does_not_depend_on_the_email_existing(self, monkeypatch):
        person(email="real@example.test")
        person(email="unusable@example.test")
        CompanyUser.objects.get(email="unusable@example.test").set_unusable_password()
        hashed = []
        original = login.check_password
        monkeypatch.setattr(
            login, "check_password", lambda *args: hashed.append(args[1]) or original(*args)
        )
        log_in("real@example.test", "not-the-password-1")
        log_in("nobody@example.test", "not-the-password-1")
        log_in("real@example.test", "a" * 3000)
        assert len(hashed) == 3  # a password is always hashed and compared, in every case
        assert hashed[1] == hashed[2] != hashed[0]  # nobody to compare to: the stand-in

    def test_the_password_is_never_in_the_answer_or_the_log(self, caplog):
        person()
        with caplog.at_level(logging.DEBUG):
            wrong = log_in(password="not-the-password-1")
            good = log_in()
        text = wrong.content.decode() + good.content.decode() + caplog.text
        assert "not-the-password-1" not in text and PASSWORD not in text
        assert "owner@example.test" not in caplog.text

    def test_the_password_is_not_accepted_in_the_address(self):
        person()
        response = APIClient(REMOTE_ADDR="203.0.113.10").get(
            f"{URL}?email=owner@example.test&password={PASSWORD}"
        )
        assert response.status_code == 405 and not Session.objects.exists()


class TestBadRequests:
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"email": "a@example.test"},
            {"password": "x"},
            {"email": 5, "password": "x"},
            {"email": "a@example.test", "password": ["x"]},
        ],
    )
    def test_both_fields_are_required_text(self, body):
        response = APIClient().post(URL, body, format="json")
        assert response.status_code == 400 and code_of(response) == "validation_error"

    def test_other_fields_are_refused(self):
        person()
        assert log_in(role="super", company_id=1).status_code == 400
