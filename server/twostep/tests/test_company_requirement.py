import pytest
from rest_framework.test import APIClient

from signin.models import Session

from .helpers import (
    PASSWORD,
    code_at,
    log_in,
    make_company_with_members,
    signed_in_client,
    turn_on,
)

BASE = "/api/auth/company/two-step/"
LOGIN_BASE = "/api/auth/company/login/two-step/"
REQUIRE = BASE + "company-requirement/"
pytestmark = pytest.mark.django_db


def post(url, body, address="203.0.113.10"):
    return APIClient(REMOTE_ADDR=address).post(url, body, format="json")


class TestOwnerSwitch:
    def test_an_owner_can_require_it_and_switch_it_off_again(self):
        company, owner, _ = make_company_with_members()
        client = signed_in_client(owner)
        assert client.put(REQUIRE, {"required": True}, format="json").json() == {"required": True}
        company.refresh_from_db()
        assert company.require_two_step
        client.put(REQUIRE, {"required": False}, format="json")
        company.refresh_from_db()
        assert not company.require_two_step

    def test_a_member_cannot_change_the_requirement(self):
        company, _, member = make_company_with_members()
        response = signed_in_client(member).put(REQUIRE, {"required": True}, format="json")
        assert response.status_code == 403 and response.json()["error"]["code"] == "not_allowed"
        company.refresh_from_db()
        assert not company.require_two_step

    def test_only_the_own_company_is_changed(self):
        company, owner, _ = make_company_with_members()
        other, _, _ = make_company_with_members("2")
        signed_in_client(owner).put(REQUIRE, {"required": True}, format="json")
        other.refresh_from_db()
        assert not other.require_two_step

    def test_the_value_must_be_yes_or_no(self):
        _, owner, _ = make_company_with_members()
        response = signed_in_client(owner).put(REQUIRE, {"required": "maybe"}, format="json")
        assert response.status_code == 400

    def test_it_needs_a_sign_in(self):
        assert APIClient().put(REQUIRE, {"required": True}, format="json").status_code == 401


class TestMembersMustSetItUp:
    @pytest.fixture
    def required(self):
        company, owner, member = make_company_with_members()
        company.require_two_step = True
        company.save()
        return company, owner, member

    def test_a_member_without_it_gets_no_session_until_they_set_it_up(self, required):
        response = log_in("member@example.test")
        assert response.json()["status"] == "two_step_setup_required"
        assert not Session.objects.filter(kind="company").exists()

    def test_the_owner_is_not_forced(self, required):
        assert log_in("owner@example.test").json() == {"status": "ok"}

    def test_setting_it_up_at_login_starts_the_session_and_shows_the_codes_once(self, required):
        challenge = log_in("member@example.test").json()["challenge"]
        started = post(LOGIN_BASE + "setup/", {"challenge": challenge}).json()
        assert started["secret"] and started["uri"].startswith("otpauth://")

        wrong = post(LOGIN_BASE + "setup/confirm/", {"challenge": challenge, "code": "000000"})
        assert wrong.status_code == 400 and not Session.objects.filter(kind="company").exists()

        done = post(
            LOGIN_BASE + "setup/confirm/",
            {"challenge": challenge, "code": code_at(started["secret"], 0)},
        )
        assert done.status_code == 200 and len(done.json()["recovery_codes"]) == 10
        assert Session.objects.filter(kind="company", status="active").exists()

        # From now on the member logs in with a code like anyone else.
        assert log_in("member@example.test").json()["status"] == "two_step_required"

    def test_a_member_who_already_has_it_just_gives_the_code(self, required):
        _, _, member = required
        secret, _ = turn_on(member)
        assert log_in("member@example.test").json()["status"] == "two_step_required"

    def test_a_member_cannot_turn_it_off_while_it_is_required(self, required):
        _, _, member = required
        secret, codes = turn_on(member)
        response = signed_in_client(member).post(
            BASE + "turn-off/", {"password": PASSWORD, "code": codes[0]}, format="json"
        )
        assert (
            response.status_code == 403 and response.json()["error"]["code"] == "two_step_required"
        )
        member.refresh_from_db()
        assert member.two_step_enabled

    def test_when_the_requirement_is_dropped_members_log_in_as_before(self, required):
        company, owner, _ = required
        company.require_two_step = False
        company.save()
        assert log_in("member@example.test").json() == {"status": "ok"}

    def test_the_setup_step_is_refused_for_someone_who_already_has_it(self, required):
        _, _, member = required
        challenge = log_in("member@example.test").json()["challenge"]
        turn_on(member)
        response = post(LOGIN_BASE + "setup/", {"challenge": challenge})
        assert response.json()["error"]["code"] == "two_step_challenge_ended"

    def test_a_suspended_company_cannot_finish_a_setup(self, required):
        company, _, _ = required
        challenge = log_in("member@example.test").json()["challenge"]
        company.status = "suspended"
        company.save()
        assert post(LOGIN_BASE + "setup/", {"challenge": challenge}).status_code == 400
