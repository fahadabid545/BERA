import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from adminusers.models import AdminUser
from core.tests.factories import make_admin_user, make_company_user
from platform_settings.service import get_setting
from signin.cookies import access_cookie_name, refresh_cookie_name
from signin.models import Session
from signin.tokens import ACCESS, REFRESH, read_token
from twostep.service import ADMIN_WRONG_CODE
from twostep.tests.helpers import code_at

PASSWORD = "violet-harbour-lantern-92"  # nosecret: fake test value
BASE = "/api/auth/admin/login/"
VERIFY = BASE + "two-step/"
SETUP = BASE + "two-step/setup/"
CONFIRM = SETUP + "confirm/"
pytestmark = pytest.mark.django_db


def admin(email="boss@example.test", **fields):
    account = make_admin_user(email=email, **fields)
    account.set_password(PASSWORD)
    account.save()
    return account


def post(path, body, address="203.0.113.20"):
    return APIClient(REMOTE_ADDR=address).post(path, body, format="json")


def password_step(email="boss@example.test", password=PASSWORD, address="203.0.113.20"):
    return post(BASE, {"email": email, "password": password}, address)


def enrolled(account=None):
    """An admin whose authenticator is set up. Returns (admin, secret)."""
    account = account or admin()
    challenge = password_step(account.email).json()["challenge"]
    secret = post(SETUP, {"challenge": challenge}).json()["secret"]
    response = post(CONFIRM, {"challenge": challenge, "code": code_at(secret, 0)})
    assert response.status_code == 200
    account.refresh_from_db()
    return account, secret


class TestThePasswordStep:
    def test_a_right_password_alone_starts_no_session(self):
        admin()
        response = password_step()
        assert response.status_code == 200
        assert response.json()["status"] == "two_step_setup_required"
        assert not response.cookies and not Session.objects.exists()

    def test_with_an_authenticator_set_up_the_code_is_asked_for(self):
        account, _ = enrolled()
        response = password_step(account.email)
        assert response.json()["status"] == "two_step_required"
        assert not response.cookies

    @pytest.mark.parametrize("status", ["blocked", "removed"])
    def test_a_blocked_or_removed_admin_gets_the_same_answer_as_a_wrong_password(self, status):
        admin("gone@example.test", status=status)
        wrong = password_step("gone@example.test", "not-the-password")
        right = password_step("gone@example.test")
        unknown = password_step("nobody@example.test")
        assert right.status_code == wrong.status_code == unknown.status_code == 400
        assert right.json() == wrong.json() == unknown.json()
        assert right.json()["error"]["code"] == "invalid_credentials"

    def test_a_company_user_cannot_use_the_admin_login(self):
        person = make_company_user(email="company@example.test")
        person.set_password(PASSWORD)
        person.save()
        response = password_step("company@example.test")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_five_wrong_passwords_pause_the_admin_like_a_company_login(self):
        admin()
        codes = [password_step(password="wrong").status_code for _ in range(5)]
        assert codes == [400, 400, 400, 400, 429]
        assert password_step().status_code == 429  # even the right password, while paused

    def test_the_admin_pause_is_not_shared_with_a_company_login_of_the_same_address(self):
        admin("shared@example.test")
        for _ in range(5):
            password_step("shared@example.test", "wrong")
        person = make_company_user(email="shared@example.test")
        person.set_password(PASSWORD)
        person.email_verified = True
        person.save()
        response = post(
            "/api/auth/company/login/", {"email": "shared@example.test", "password": PASSWORD}
        )
        assert response.status_code == 200


class TestSettingUpTheAuthenticator:
    def test_finishing_the_setup_starts_the_session_with_no_recovery_codes(self):
        account = admin()
        challenge = password_step().json()["challenge"]
        secret = post(SETUP, {"challenge": challenge}).json()["secret"]
        response = post(CONFIRM, {"challenge": challenge, "code": code_at(secret, 0)})
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "recovery_codes": []}
        assert access_cookie_name("admin") in response.cookies
        account.refresh_from_db()
        assert account.two_step_enabled
        assert Session.objects.get().kind == "admin"

    def test_a_wrong_code_does_not_finish_the_setup(self):
        account = admin()
        challenge = password_step().json()["challenge"]
        post(SETUP, {"challenge": challenge})
        response = post(CONFIRM, {"challenge": challenge, "code": "000000"})
        assert response.status_code == 400
        assert not response.cookies and not Session.objects.exists()
        account.refresh_from_db()
        assert not account.two_step_enabled

    def test_setup_is_refused_once_an_authenticator_is_in_use(self):
        account, _ = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        assert post(SETUP, {"challenge": challenge}).status_code == 400  # wrong purpose


class TestTheCodeStep:
    def test_a_right_code_starts_the_session(self):
        account, secret = enrolled()
        Session.objects.all().delete()
        challenge = password_step(account.email).json()["challenge"]
        response = post(VERIFY, {"challenge": challenge, "code": code_at(secret, 1)})
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert access_cookie_name("admin") in response.cookies
        assert refresh_cookie_name("admin") in response.cookies
        assert Session.objects.get().user_id == account.pk

    def test_a_wrong_code_starts_no_session_and_points_to_another_super_admin(self):
        account, _ = enrolled()
        Session.objects.all().delete()
        challenge = password_step(account.email).json()["challenge"]
        response = post(VERIFY, {"challenge": challenge, "code": "000000"})
        assert response.status_code == 400
        assert response.json()["error"]["message"] == ADMIN_WRONG_CODE
        assert "super admin" in ADMIN_WRONG_CODE
        assert not response.cookies and not Session.objects.exists()

    def test_a_used_code_cannot_be_used_again(self):
        account, secret = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        # the setup already used the current step
        assert post(VERIFY, {"challenge": challenge, "code": code_at(secret, 0)}).status_code == 400

    def test_a_recovery_style_code_is_never_accepted(self):
        account, _ = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        response = post(VERIFY, {"challenge": challenge, "code": "ABCDE-FGHJK"})
        assert response.status_code == 400 and not response.cookies

    def test_five_wrong_codes_pause_the_code_guessing(self):
        account, secret = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        codes = [
            post(VERIFY, {"challenge": challenge, "code": "000000"}).status_code for _ in range(5)
        ]
        assert codes == [400, 400, 400, 400, 429]
        assert post(VERIFY, {"challenge": challenge, "code": code_at(secret, 1)}).status_code == 429

    def test_a_challenge_from_the_company_login_does_not_open_an_admin_session(self):
        from twostep.challenge import VERIFY as VERIFY_PURPOSE
        from twostep.challenge import make_challenge

        person = make_company_user()
        challenge = make_challenge(person, VERIFY_PURPOSE)
        response = post(VERIFY, {"challenge": challenge, "code": "000000"})
        assert response.json()["error"]["code"] == "two_step_challenge_ended"

    def test_an_admin_challenge_does_not_open_a_company_session(self):
        from signin.kinds import ADMIN
        from twostep.challenge import VERIFY as VERIFY_PURPOSE
        from twostep.challenge import make_challenge

        account, _ = enrolled()
        challenge = make_challenge(account, VERIFY_PURPOSE, ADMIN)
        response = post(
            "/api/auth/company/login/two-step/", {"challenge": challenge, "code": "000000"}
        )
        assert response.json()["error"]["code"] == "two_step_challenge_ended"

    def test_the_step_ends_after_the_agreed_minutes(self):
        account, secret = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        later = time.time() + get_setting("two_step.challenge_minutes") * 60 + 5
        with patch("django.core.signing.time.time", return_value=later):
            response = post(VERIFY, {"challenge": challenge, "code": code_at(secret, 1)})
        assert response.json()["error"]["code"] == "two_step_challenge_ended"

    def test_a_blocked_admin_cannot_finish_a_login_already_begun(self):
        account, secret = enrolled()
        challenge = password_step(account.email).json()["challenge"]
        AdminUser.objects.filter(pk=account.pk).update(status="blocked")
        response = post(VERIFY, {"challenge": challenge, "code": code_at(secret, 1)})
        assert response.json()["error"]["code"] == "two_step_challenge_ended"


class TestAdminSessionLifetimes:
    def test_the_access_token_lasts_10_minutes_and_the_refresh_token_8_hours(self):
        assert get_setting("tokens.admin_access_minutes") == 10
        assert get_setting("tokens.admin_refresh_hours") == 8
        account, _ = enrolled()
        cookies = Session.objects.get()
        response_cookies = _login_cookies(account)
        assert response_cookies[access_cookie_name("admin")]["max-age"] == 600
        assert response_cookies[refresh_cookie_name("admin")]["max-age"] == 8 * 3600
        access = read_token(
            response_cookies[access_cookie_name("admin")].value, kind="admin", token_type=ACCESS
        )
        refresh = read_token(
            response_cookies[refresh_cookie_name("admin")].value, kind="admin", token_type=REFRESH
        )
        assert access["exp"] - access["iat"] == 600
        assert refresh["exp"] - refresh["iat"] == 8 * 3600
        newest = Session.objects.exclude(pk=cookies.pk).get()
        assert (
            timedelta(hours=7, minutes=59)
            < newest.expires_at - timezone.now()
            <= timedelta(hours=8)
        )

    def test_company_sessions_keep_their_own_lifetimes(self):
        from signin import service

        person = make_company_user()
        issued = service.start_session(
            user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
        )
        assert issued.access_seconds == get_setting("tokens.access_minutes") * 60
        assert issued.refresh_seconds == get_setting("tokens.refresh_days") * 86400

    def test_a_renewed_admin_session_gets_the_admin_lifetimes_again(self):
        account, _ = enrolled()
        client = _login_client(account)
        refresh_value = client.cookies[refresh_cookie_name("admin")].value
        csrf = client.cookies["bera_csrf"].value
        fresh = APIClient(REMOTE_ADDR="203.0.113.20", HTTP_X_CSRF_TOKEN=csrf)
        fresh.cookies[refresh_cookie_name("admin")] = refresh_value
        fresh.cookies["bera_csrf"] = csrf
        response = fresh.post("/api/auth/admin/refresh/")
        assert response.status_code == 200
        assert response.cookies[access_cookie_name("admin")]["max-age"] == 600
        assert response.cookies[refresh_cookie_name("admin")]["max-age"] == 8 * 3600


def _login_client(account):
    """A client signed in through the whole admin login, with its cookies."""
    secret = account.two_step_secret
    challenge = password_step(account.email).json()["challenge"]
    client = APIClient(REMOTE_ADDR="203.0.113.20")
    # the setup used step 0, so the next step's code is accepted (one step of drift)
    response = client.post(
        VERIFY, {"challenge": challenge, "code": code_at(secret, 1)}, format="json"
    )
    assert response.status_code == 200
    return client


def _login_cookies(account):
    return _login_client(account).cookies


class TestThereIsNoPublicAdminSignUp:
    @pytest.mark.parametrize(
        "path", ["sign-up", "signup", "register", "create", "invite", "accept-invite"]
    )
    def test_no_admin_account_can_be_made_from_outside(self, path):
        response = APIClient().post(
            f"/api/auth/admin/{path}/",
            {"email": "new@example.test", "password": PASSWORD, "name": "X"},
            format="json",
        )
        assert response.status_code == 404
        assert not AdminUser.objects.filter(email="new@example.test").exists()
