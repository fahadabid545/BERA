"""One set of password rules wherever a person chooses a password.

Every place that sets a password is listed here and must refuse the same passwords with the
same reasons. When the team-invite acceptance exists it joins this list.
"""

import pytest
from rest_framework.test import APIClient

from core.passwords import PasswordField, password_problems, password_rule_results
from core.tests.factories import make_company_user
from emailing.link_tokens import issue_link_token
from signin import service
from signin.cookies import CSRF_COOKIE, access_cookie_name

pytestmark = pytest.mark.django_db

GOOD = "copper-meadow-lantern-58"  # nosecret: fake test value
CURRENT = "violet-harbour-lantern-92"  # nosecret: fake test value
WEAK = {
    "too short": ("Sh0rt-one", "Use at least 12 characters."),
    "too common": ("123456789qwerty", "too common"),
    "too long": ("a1" * 70, "Use at most 128 characters."),
}


def sign_up(password):
    body = {
        "company_name": "Fake Ltd",
        "name": "Fake Owner",
        "email": "new.owner@example.test",
        "password": password,
        "country": "DE",
        "accept_terms": True,
    }
    return APIClient(REMOTE_ADDR="203.0.113.1").post(
        "/api/auth/company/signup/", body, format="json"
    )


def reset(password):
    person = make_company_user(role="member")
    token = issue_link_token("reset_password", person.pk, 1)
    body = {"token": token, "password": password, "confirm_password": password}
    return APIClient(REMOTE_ADDR="203.0.113.2").post(
        "/api/auth/company/reset-password/", body, format="json"
    )


def change(password):
    person = make_company_user(role="member")
    person.set_password(CURRENT)
    person.save()
    issued = service.start_session(
        user_id=person.pk, role="member", company_id=person.company_id, kind="company"
    )
    client = APIClient(REMOTE_ADDR="203.0.113.3")
    client.cookies[access_cookie_name("company")] = issued.access_token
    client.cookies[CSRF_COOKIE] = "csrf"
    body = {"current_password": CURRENT, "password": password, "confirm_password": password}
    return client.post(
        "/api/auth/company/change-password/", body, format="json", HTTP_X_CSRF_TOKEN="csrf"
    )


PLACES = {"sign up": sign_up, "reset": reset, "profile": change}


@pytest.mark.parametrize("place", PLACES)
@pytest.mark.parametrize("weakness", WEAK)
def test_a_weak_password_is_refused_with_its_reason_everywhere(place, weakness):
    password, reason = WEAK[weakness]
    response = PLACES[place](password)
    assert response.status_code == 400
    assert reason in response.json()["error"]["fields"]["password"]


@pytest.mark.parametrize("place", PLACES)
def test_every_reason_is_shown_together_everywhere(place):
    message = PLACES[place]("password").json()["error"]["fields"]["password"]
    assert "at least 12 characters" in message and "too common" in message


@pytest.mark.parametrize("place", PLACES)
def test_a_good_password_is_accepted_everywhere(place):
    assert PLACES[place](GOOD).status_code == 200


@pytest.mark.parametrize("place", PLACES)
def test_the_limits_are_the_platform_settings_everywhere(place):
    from platform_settings.models import PlatformSetting

    PlatformSetting.objects.create(key="passwords.min_length", value=30)
    message = PLACES[place](GOOD).json()["error"]["fields"]["password"]
    assert message == "Use at least 30 characters."


def test_the_serializers_use_the_shared_rules():
    from companies.serializers import ResetPasswordSerializer, SignUpSerializer

    for serializer in (SignUpSerializer, ResetPasswordSerializer):
        assert isinstance(serializer().fields["password"], PasswordField)


class TestTheLiveHints:
    def test_each_rule_says_whether_it_is_met(self):
        results = {rule["id"]: rule for rule in password_rule_results("short")}
        assert [rule["met"] for rule in results.values()] == [False, True, True]
        assert results["min_length"]["text"] == "At least 12 characters"
        assert results["max_length"]["text"] == "At most 128 characters"
        assert results["not_common"]["text"] == "Not a commonly used password"

    def test_a_good_password_meets_them_all(self):
        assert all(rule["met"] for rule in password_rule_results(GOOD))

    def test_the_hints_and_the_refusals_always_agree(self):
        for password in ["", "short", "123456789qwerty", GOOD, "a1" * 70, "password1234"]:
            unmet = [rule for rule in password_rule_results(password) if not rule["met"]]
            assert len(unmet) == len(password_problems(password))

    def test_the_common_password_rule_disappears_when_switched_off(self):
        from platform_settings.models import PlatformSetting

        PlatformSetting.objects.create(key="passwords.block_common_passwords", value=False)
        assert "not_common" not in [rule["id"] for rule in password_rule_results("password")]
        assert password_problems("123456789qwerty") == []


class TestTheCheckingRoute:
    URL = "/api/auth/password-check/"

    def check(self, password):
        return APIClient(REMOTE_ADDR="203.0.113.9").post(
            self.URL, {"password": password}, format="json"
        )

    def test_it_reports_each_rule_without_needing_an_account(self):
        response = self.check("password")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert [rule["met"] for rule in body["rules"]] == [False, True, False]

    def test_a_good_password_is_ok(self):
        assert self.check(GOOD).json()["ok"] is True

    def test_an_empty_password_is_not_ok_and_not_an_error(self):
        assert self.check("").json()["ok"] is False

    @pytest.mark.parametrize("body", [{}, {"password": 5}, {"password": GOOD, "extra": 1}])
    def test_a_bad_request_is_refused(self, body):
        assert APIClient().post(self.URL, body, format="json").status_code == 400

    def test_it_does_not_echo_or_log_the_password(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG):
            response = self.check(GOOD)
        assert GOOD not in response.content.decode() + caplog.text

    def test_only_the_post_method_is_allowed(self):
        assert APIClient().get(self.URL + "?password=x").status_code == 405
