import logging
import re

import pytest
from rest_framework.exceptions import NotAuthenticated
from rest_framework.test import APIClient

from core.tests.factories import make_company_user
from emailing.models import OutgoingEmail
from platform_settings.models import PlatformSetting
from signin import service
from signin.cookies import CSRF_COOKIE, access_cookie_name, refresh_cookie_name
from signin.models import Session

URL = "/api/auth/company/change-password/"
LOGIN = "/api/auth/company/login/"
CURRENT = "violet-harbour-lantern-92"  # nosecret: fake test value
NEW = "copper-meadow-lantern-58"  # nosecret: fake test value
CSRF = "csrf-value"

pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    person = make_company_user(email="owner@example.test", name="Fake Owner", email_verified=True)
    person.set_password(CURRENT)
    person.save()
    return person


def sign_in(person):
    issued = service.start_session(
        user_id=person.pk, role=person.role, company_id=person.company_id, kind="company"
    )
    client = APIClient(REMOTE_ADDR="203.0.113.5")
    client.cookies[access_cookie_name("company")] = issued.access_token
    client.cookies[refresh_cookie_name("company")] = issued.refresh_token
    client.cookies[CSRF_COOKIE] = CSRF
    return client, issued


def change(client, current=CURRENT, new=NEW, confirm=None, **extra):
    body = {
        "current_password": current,
        "password": new,
        "confirm_password": new if confirm is None else confirm,
        **extra,
    }
    return client.post(URL, body, format="json", HTTP_X_CSRF_TOKEN=CSRF)


def log_in(password):
    return APIClient(REMOTE_ADDR="203.0.113.50").post(
        LOGIN, {"email": "owner@example.test", "password": password}, format="json"
    )


def fields_of(response):
    return response.json()["error"]["fields"]


def refused(issued):
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.access_token, "company")


class TestChangingIt:
    def test_the_new_password_replaces_the_current_one(self, account):
        client, _ = sign_in(account)
        response = change(client)
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert log_in(NEW).status_code == 200 and log_in(CURRENT).status_code == 400

    def test_every_other_session_ends(self, account):
        client, this_device = sign_in(account)
        _, other_device = sign_in(account)
        change(client)
        refused(other_device)
        refused(this_device)  # its tokens ended too; a fresh pair is issued just below

    def test_this_device_stays_signed_in_with_new_protected_cookies(self, account):
        client, old = sign_in(account)
        response = change(client)
        access = response.cookies[access_cookie_name("company")]
        assert access["httponly"] and access.value != old.access_token
        user = service.verify_access_token(access.value, "company")
        assert (user.user_id, user.role) == (account.pk, account.role)
        assert Session.objects.filter(status="active").count() == 1

    def test_other_peoples_sessions_are_untouched(self, account):
        client, _ = sign_in(account)
        _, theirs = sign_in(make_company_user(role="member"))
        change(client)
        assert service.verify_access_token(theirs.access_token, "company")

    def test_a_notification_email_follows(self, account):
        client, _ = sign_in(account)
        change(client)
        email = OutgoingEmail.objects.get(template="password_changed")
        assert email.to_address == "owner@example.test"
        assert "Fake Owner" in email.text_body and "UTC" in email.text_body
        assert CURRENT not in email.text_body and NEW not in email.text_body

    def test_the_password_is_stored_only_as_a_strong_hash(self, account):
        client, _ = sign_in(account)
        change(client)
        account.refresh_from_db()
        assert account.password_hash.startswith("argon2$") and NEW not in account.password_hash


class TestRefusedChanges:
    def test_a_wrong_current_password_gets_one_plain_message_and_no_hints(self, account):
        client, _ = sign_in(account)
        response = change(client, current="not-the-password-1", new="weak", confirm="other")
        assert response.status_code == 400
        assert fields_of(response) == {"current_password": "Your current password is incorrect."}
        assert not OutgoingEmail.objects.filter(template="password_changed").exists()
        assert log_in(CURRENT).status_code == 200  # nothing changed

    def test_a_wrong_current_password_changes_nothing_and_keeps_the_sessions(self, account):
        client, issued = sign_in(account)
        change(client, current="not-the-password-1")
        assert service.verify_access_token(issued.access_token, "company")

    def test_repeated_wrong_entries_pause_the_account(self, account):
        client, _ = sign_in(account)
        statuses = [change(client, current="not-the-password-1").status_code for _ in range(5)]
        assert statuses == [400, 400, 400, 400, 429]

    def test_the_pause_also_stops_logging_in_and_changing_with_the_right_password(self, account):
        client, _ = sign_in(account)
        for _ in range(5):
            change(client, current="not-the-password-1")
        assert log_in(CURRENT).status_code == 429
        assert change(client).status_code == 429

    def test_wrong_guesses_at_login_and_here_add_up(self, account):
        client, _ = sign_in(account)
        for _ in range(3):
            log_in("not-the-password-1")
        statuses = [change(client, current="not-the-password-1").status_code for _ in range(2)]
        assert statuses == [400, 429]

    def test_the_right_current_password_clears_the_count(self, account):
        client, _ = sign_in(account)
        for _ in range(4):
            change(client, current="not-the-password-1")
        assert change(client).status_code == 200
        client, _ = sign_in(account)
        assert [
            change(client, current="not-the-password-1", new=CURRENT).status_code for _ in range(4)
        ] == [400] * 4

    def test_the_numbers_are_the_same_platform_settings_as_login(self, account):
        PlatformSetting.objects.create(key="signin.max_failed_attempts", value=2)
        client, _ = sign_in(account)
        statuses = [change(client, current="not-the-password-1").status_code for _ in range(2)]
        assert statuses == [400, 429]

    def test_a_weak_new_password_is_refused_with_the_reasons(self, account):
        client, issued = sign_in(account)
        response = change(client, new="password")
        message = fields_of(response)["password"]
        assert "at least 12 characters" in message and "too common" in message
        assert service.verify_access_token(issued.access_token, "company")

    def test_the_two_new_entries_must_match(self, account):
        client, _ = sign_in(account)
        response = change(client, confirm=NEW + "x")
        assert fields_of(response) == {"confirm_password": "The passwords do not match."}
        assert log_in(CURRENT).status_code == 200

    def test_the_new_password_cannot_be_the_current_one(self, account):
        client, _ = sign_in(account)
        response = change(client, new=CURRENT)
        assert (
            fields_of(response)["password"]
            == "Your new password must be different from your old one."
        )

    @pytest.mark.parametrize("missing", ["current_password", "password", "confirm_password"])
    def test_every_field_is_required(self, account, missing):
        client, _ = sign_in(account)
        body = {"current_password": CURRENT, "password": NEW, "confirm_password": NEW}
        del body[missing]
        response = client.post(URL, body, format="json", HTTP_X_CSRF_TOKEN=CSRF)
        assert response.status_code == 400 and missing in fields_of(response)

    def test_other_fields_are_refused(self, account):
        client, _ = sign_in(account)
        assert change(client, email="someone.else@example.test").status_code == 400

    def test_passwords_are_never_in_an_answer_or_the_log(self, account, caplog):
        client, _ = sign_in(account)
        with caplog.at_level(logging.DEBUG):
            bad = change(client, current="not-the-password-1")
            good = change(client)
        text = bad.content.decode() + good.content.decode() + caplog.text
        for secret in ("not-the-password-1", CURRENT, NEW):
            assert secret not in text


class TestWhoMayChangeIt:
    def test_only_signed_in_people(self, account):
        assert change(APIClient(REMOTE_ADDR="203.0.113.5")).status_code == 401

    def test_another_site_cannot_do_it(self, account):
        client, _ = sign_in(account)
        response = client.post(
            URL,
            {"current_password": CURRENT, "password": NEW, "confirm_password": NEW},
            format="json",
            HTTP_X_CSRF_TOKEN="something-else",
        )
        assert response.status_code == 403 and log_in(CURRENT).status_code == 200

    def test_an_admin_session_cannot_change_a_company_users_password(self, account):
        from core.tests.factories import make_admin_user

        admin = make_admin_user()
        issued = service.start_session(
            user_id=admin.pk, role="super", company_id=None, kind="admin"
        )
        client = APIClient(
            HTTP_AUTHORIZATION=f"Bearer {issued.access_token}", REMOTE_ADDR="203.0.113.5"
        )
        response = client.post(
            URL,
            {"current_password": CURRENT, "password": NEW, "confirm_password": NEW},
            format="json",
        )
        assert response.status_code == 401

    def test_a_person_changes_only_their_own_password(self, account):
        other = make_company_user(email="other@example.test", role="member")
        other.set_password("other-persons-password-77")
        other.save()
        client, _ = sign_in(account)
        change(client)
        other.refresh_from_db()
        assert other.check_password("other-persons-password-77")


def test_the_link_in_the_email_leads_to_forgot_password(account):
    client, _ = sign_in(account)
    change(client)
    text = OutgoingEmail.objects.get(template="password_changed").text_body
    assert re.search(r"http://localhost:3000/forgot-password", text)
