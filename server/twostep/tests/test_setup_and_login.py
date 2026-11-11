import time
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from platform_settings.service import get_setting
from signin.models import Session
from twostep.models import RecoveryCode
from twostep.recovery_codes import normalise
from twostep.service import LOST_DEVICE

from .helpers import (
    LOGIN,
    code_at,
    log_in,
    make_company_with_members,
    person,
    signed_in_client,
    turn_on,
)

BASE = "/api/auth/company/two-step/"
VERIFY = "/api/auth/company/login/two-step/"
pytestmark = pytest.mark.django_db


def second_step(challenge, code, address="203.0.113.10"):
    return APIClient(REMOTE_ADDR=address).post(
        VERIFY, {"challenge": challenge, "code": code}, format="json"
    )


class TestSettingItUp:
    def test_setup_gives_a_secret_and_a_link_for_the_authenticator_app(self):
        account = person()
        body = signed_in_client(account).post(BASE + "setup/").json()
        assert body["uri"].startswith("otpauth://totp/") and body["secret"] in body["uri"]
        account.refresh_from_db()
        assert account.two_step_secret == body["secret"] and not account.two_step_enabled

    def test_it_only_counts_once_a_right_code_is_given(self):
        account = person()
        client = signed_in_client(account)
        secret = client.post(BASE + "setup/").json()["secret"]

        wrong = client.post(BASE + "setup/confirm/", {"code": "000000"}, format="json")
        assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "two_step_code_wrong"
        account.refresh_from_db()
        assert not account.two_step_enabled

        right = client.post(BASE + "setup/confirm/", {"code": code_at(secret, 0)}, format="json")
        assert right.status_code == 200
        account.refresh_from_db()
        assert account.two_step_enabled

    def test_ten_recovery_codes_are_shown_once_and_stored_only_as_hashes(self):
        account = person()
        _, codes = turn_on(account)
        assert len(codes) == 10 and len(set(codes)) == 10
        stored = {row.code_hash for row in RecoveryCode.objects.filter(user=account)}
        assert len(stored) == 10
        assert not any(
            normalise(code) in hash_ or code in hash_ for code in codes for hash_ in stored
        )
        # No route gives them out again.
        status = signed_in_client(account).get(BASE).json()
        assert status["recovery_codes_left"] == 10 and "recovery_codes" not in status

    def test_the_secret_is_stored_encrypted(self):
        from django.db import connection

        account = person()
        secret, _ = turn_on(account)
        with connection.cursor() as cursor:
            cursor.execute(
                "select two_step_secret from companies_companyuser where id=%s", [account.pk]
            )
            assert secret not in cursor.fetchone()[0]

    def test_it_cannot_be_set_up_twice(self):
        account = person()
        turn_on(account)
        response = signed_in_client(account).post(BASE + "setup/")
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "two_step_already_on"
        )

    def test_the_routes_need_a_sign_in(self):
        for method, route in (
            ("get", ""),
            ("post", "setup/"),
            ("post", "setup/confirm/"),
            ("post", "turn-off/"),
        ):
            assert getattr(APIClient(), method)(BASE + route).status_code == 401


class TestLoggingInWithIt:
    def test_a_right_password_alone_does_not_start_a_session(self):
        account = person()
        turn_on(account)
        Session.objects.all().delete()
        response = log_in()
        assert response.status_code == 200
        assert response.json()["status"] == "two_step_required" and response.json()["challenge"]
        assert not Session.objects.exists() and not response.cookies

    def test_the_app_code_finishes_the_login(self):
        account = person()
        secret, _ = turn_on(account)
        challenge = log_in().json()["challenge"]
        response = second_step(challenge, code_at(secret, 1))
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert Session.objects.filter(user_id=account.pk, status="active").exists()
        assert any(name.startswith("bera_company") for name in response.cookies)

    def test_a_wrong_code_is_refused_without_a_session(self):
        account = person()
        turn_on(account)
        Session.objects.all().delete()
        response = second_step(log_in().json()["challenge"], "123456")
        assert response.status_code == 400 and not Session.objects.exists()

    def test_a_code_cannot_be_used_twice(self):
        account = person()
        secret, _ = turn_on(account)
        code = code_at(secret, 1)
        assert second_step(log_in().json()["challenge"], code).status_code == 200
        assert second_step(log_in().json()["challenge"], code).status_code == 400

    def test_the_code_from_the_setup_step_cannot_be_reused_either(self):
        account = person()
        secret, _ = turn_on(account)
        assert second_step(log_in().json()["challenge"], code_at(secret, 0)).status_code == 400

    def test_an_old_code_outside_the_drift_is_refused(self):
        account = person()
        secret, _ = turn_on(account)
        assert second_step(log_in().json()["challenge"], code_at(secret, 3)).status_code == 400

    def test_the_wrong_password_never_gets_to_the_second_step(self):
        person()
        response = APIClient().post(
            LOGIN, {"email": "owner@example.test", "password": "wrong"}, format="json"
        )
        assert response.json()["error"]["code"] == "invalid_credentials"


class TestRecoveryCodes:
    def test_a_recovery_code_logs_in_once(self):
        account = person()
        _, codes = turn_on(account)
        assert second_step(log_in().json()["challenge"], codes[0]).status_code == 200
        assert second_step(log_in().json()["challenge"], codes[0]).status_code == 400
        status = signed_in_client(account).get(BASE).json()
        assert status["recovery_codes_left"] == 9

    def test_case_and_spacing_do_not_matter(self):
        account = person()
        _, codes = turn_on(account)
        sloppy = codes[1].lower().replace("-", " ")
        assert second_step(log_in().json()["challenge"], sloppy).status_code == 200

    def test_a_made_up_code_is_refused(self):
        account = person()
        turn_on(account)
        assert second_step(log_in().json()["challenge"], "AAAAA-AAAAA").status_code == 400

    def test_another_persons_recovery_code_does_not_work(self):
        first, second = person(), person("other@example.test")
        turn_on(first)
        _, other_codes = turn_on(second)
        assert second_step(log_in().json()["challenge"], other_codes[0]).status_code == 400

    def test_the_lost_device_message_tells_what_to_do(self):
        assert "Contact support" in LOST_DEVICE and "recovery codes" in LOST_DEVICE


class TestGuessingCodes:
    def test_repeated_wrong_codes_pause_the_account(self):
        account = person()
        turn_on(account)
        challenge = log_in().json()["challenge"]
        statuses = [second_step(challenge, "000000").status_code for _ in range(5)]
        assert statuses == [400, 400, 400, 400, 429]
        # Even the right code is refused while paused.
        secret = account.__class__.objects.get(pk=account.pk).two_step_secret
        assert second_step(challenge, code_at(secret, 1)).status_code == 429

    def test_logging_in_again_does_not_reset_the_count(self):
        account = person()
        turn_on(account)
        for _ in range(4):
            second_step(log_in().json()["challenge"], "000000")
        assert second_step(log_in().json()["challenge"], "000000").status_code == 429


class TestTheChallenge:
    def test_a_made_up_challenge_is_refused(self):
        response = second_step("not-a-challenge", "123456")
        assert (
            response.status_code == 400
            and response.json()["error"]["code"] == "two_step_challenge_ended"
        )

    def test_a_challenge_ends_after_the_platform_setting(self):
        account = person()
        secret, _ = turn_on(account)
        challenge = log_in().json()["challenge"]
        minutes = get_setting("two_step.challenge_minutes")

        with patch("time.time", return_value=time.time() + (minutes + 1) * 60):
            late = second_step(challenge, code_at(secret, 1))
        assert (
            late.status_code == 400 and late.json()["error"]["code"] == "two_step_challenge_ended"
        )

        with patch("time.time", return_value=time.time() + (minutes - 1) * 60):
            assert second_step(challenge, code_at(secret, 1)).status_code == 200

    def test_a_setup_challenge_cannot_be_used_to_give_a_code(self):
        company, owner, member = make_company_with_members()
        company.require_two_step = True
        company.save()
        challenge = log_in("member@example.test").json()["challenge"]
        assert (
            second_step(challenge, "123456").json()["error"]["code"] == "two_step_challenge_ended"
        )

    def test_a_blocked_person_cannot_finish_a_login(self):
        account = person()
        secret, _ = turn_on(account)
        challenge = log_in().json()["challenge"]
        account.status = "blocked"
        account.save()
        assert second_step(challenge, code_at(secret, 1)).status_code == 400


class TestTurningItOff:
    def test_it_needs_the_password_and_a_code(self):
        from .helpers import PASSWORD

        account = person()
        secret, codes = turn_on(account)
        client = signed_in_client(account)
        url = BASE + "turn-off/"

        no_code = client.post(url, {"password": PASSWORD, "code": "000000"}, format="json")
        wrong_password = client.post(
            url, {"password": "wrong-one", "code": codes[0]}, format="json"
        )
        assert (no_code.status_code, wrong_password.status_code) == (400, 400)
        account.refresh_from_db()
        assert account.two_step_enabled and RecoveryCode.objects.filter(user=account).count() == 10

        done = client.post(url, {"password": PASSWORD, "code": codes[0]}, format="json")
        assert done.status_code == 200
        account.refresh_from_db()
        assert not account.two_step_enabled and account.two_step_secret == ""
        assert not RecoveryCode.objects.filter(user=account).exists()
        assert log_in().json() == {"status": "ok"}

    def test_it_cannot_be_turned_off_when_it_is_not_on(self):
        from .helpers import PASSWORD

        response = signed_in_client(person()).post(
            BASE + "turn-off/", {"password": PASSWORD, "code": "123456"}, format="json"
        )
        assert response.json()["error"]["code"] == "two_step_not_on"
