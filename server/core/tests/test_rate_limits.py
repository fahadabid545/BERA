from datetime import UTC, datetime, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core import rate_limits
from core.models import BlockedSource, RateCounter
from core.tests.factories import make_company_user
from signin import service

pytestmark = [pytest.mark.urls("core.tests.urls_for_limits"), pytest.mark.django_db]

# A moment on a whole hour, so no counting window ends in the middle of a test.
START = datetime(2030, 1, 1, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.current = START

    def advance(self, **delta):
        self.current += timedelta(**delta)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(rate_limits, "now", lambda: fake.current)
    return fake


def person(company_id=3, role="owner"):
    """A signed-in company user, as a client that sends its token."""
    user = make_company_user()
    issued = service.start_session(
        user_id=user.id, role=role, company_id=company_id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def visitor(address="203.0.113.9"):
    return APIClient(REMOTE_ADDR=address)


def statuses(client, path, times, **extra):
    return [client.post(path, **extra).status_code for _ in range(times)]


@pytest.mark.parametrize(
    ("path", "limit"),
    [("/api/login/", 10), ("/api/sign-up/", 5), ("/api/contact/", 3)],
)
def test_address_limits_allow_exactly_the_limit_then_refuse(path, limit):
    client = visitor()
    answers = statuses(client, path, limit + 1)
    assert answers == [200] * limit + [429]


def test_limits_are_per_address():
    assert statuses(visitor("203.0.113.1"), "/api/contact/", 4)[-1] == 429
    assert statuses(visitor("203.0.113.2"), "/api/contact/", 3) == [200] * 3


def test_password_reset_is_limited_per_email_whatever_the_address():
    def ask(address, email):
        return visitor(address).post("/api/password-reset/", {"email": email}, format="json")

    answers = [ask(f"203.0.113.{n}", "Ada@Example.com ").status_code for n in range(1, 6)]
    assert answers == [200] * 5
    assert ask("203.0.113.50", "ada@example.com").status_code == 429  # same email, new address
    assert ask("203.0.113.50", "bob@example.com").status_code == 200  # someone else's inbox


@pytest.mark.parametrize("body", [{}, {"email": ""}, {"email": 5}, {"email": ["a"]}])
def test_password_reset_without_a_usable_email_is_limited_by_address(body):
    client = visitor()
    answers = [
        client.post("/api/password-reset/", body, format="json").status_code for _ in range(6)
    ]
    assert answers == [200] * 5 + [429]


def test_invites_are_limited_to_20_an_hour_per_company_not_per_person():
    first, second = person(company_id=3), person(company_id=3)
    assert statuses(first, "/api/invites/", 12) == [200] * 12
    answers = statuses(second, "/api/invites/", 9)  # a colleague shares the company's allowance
    assert answers == [200] * 8 + [429]


def upload(client, files):
    data = {"files": [SimpleUploadedFile(f"cv{n}.pdf", b"fake") for n in range(files)]}
    return client.post("/api/uploads/", data, format="multipart").status_code


def test_uploads_allow_100_files_per_10_minutes_per_company(clock):
    client = person(company_id=3)
    assert upload(client, 60) == 200
    assert upload(client, 40) == 200
    assert upload(client, 1) == 429
    clock.advance(minutes=10)
    assert upload(client, 1) == 200  # the window has passed


def test_a_batch_that_would_go_over_the_allowance_is_refused_whole():
    client = person(company_id=3)
    assert upload(client, 60) == 200
    assert upload(client, 41) == 429


def test_downloads_are_limited_to_60_a_minute_per_user():
    colleague = person(company_id=3)
    client = person(company_id=3)
    assert statuses(client, "/api/downloads/", 60) == [200] * 60
    assert client.post("/api/downloads/").status_code == 429
    assert colleague.post("/api/downloads/").status_code == 200


def test_everything_else_is_limited_to_120_a_minute_per_user():
    client = person()
    answers = statuses(client, "/api/anything/", 121)
    assert answers == [200] * 120 + [429]
    assert person().post("/api/anything/").status_code == 200


def test_counting_starts_again_in_the_next_window(clock):
    client = visitor()
    assert statuses(client, "/api/contact/", 4)[-1] == 429
    clock.advance(hours=1)
    assert statuses(client, "/api/contact/", 3) == [200] * 3


def test_one_companys_heavy_use_never_touches_another(clock):
    busy, calm = person(company_id=3), person(company_id=4)
    assert statuses(busy, "/api/invites/", 25)[-1] == 429
    for _ in range(10):  # even the busy company's abuse leaves others alone
        busy.post("/api/invites/")
    assert statuses(calm, "/api/invites/", 20) == [200] * 20


class TestTheRefusalMessage:
    def refusal(self, path, allowed):
        client = visitor()
        statuses(client, path, allowed)
        return client.post(path)

    def test_says_how_long_to_wait_in_minutes(self, clock):
        clock.advance(minutes=30)
        response = self.refusal("/api/contact/", 3)
        error = response.json()["error"]
        assert response.status_code == 429
        assert error["code"] == "too_many_requests"
        assert error["message"] == "Too many attempts. Try again in 30 minutes."
        assert error["details"] == {"retry_after_seconds": 1800}
        assert response["Retry-After"] == "1800"

    def test_says_one_minute_not_a_fraction(self, clock):
        clock.advance(seconds=20)
        assert self.refusal("/api/login/", 10).json()["error"]["message"] == (
            "Too many attempts. Try again in 1 minute."
        )

    def test_has_no_internal_details(self):
        text = self.refusal("/api/login/", 10).content.decode()
        for internal in ("rate_limits", "203.0.113", "Throttle", "Traceback"):
            assert internal not in text


class TestBlockingRepeatedAbuse:
    def hammer(self, client, extra_attempts):
        statuses(client, "/api/login/", 10)  # use up the allowance
        return statuses(client, "/api/login/", extra_attempts)

    def test_repeated_refusals_block_the_source_for_15_minutes(self, clock):
        client = visitor()
        answers = self.hammer(client, 6)
        assert answers == [429] * 6
        blocked = client.post("/api/login/")
        assert blocked.json()["error"]["message"] == "Too many attempts. Try again in 15 minutes."

        clock.advance(minutes=14)
        assert client.post("/api/login/").json()["error"]["message"].endswith("in 1 minute.")
        clock.advance(minutes=2)
        assert client.post("/api/login/").status_code == 200

    def test_a_blocked_source_is_blocked_everywhere_not_just_where_it_misbehaved(self):
        client = visitor()
        self.hammer(client, 5)
        assert client.post("/api/sign-up/").status_code == 429
        assert visitor("203.0.113.77").post("/api/sign-up/").status_code == 200

    def test_a_few_refusals_spread_over_a_long_time_do_not_block(self, clock):
        client = visitor()
        for _ in range(8):
            self.hammer(client, 1)  # one refusal ...
            clock.advance(minutes=15)  # ... then a long quiet time
        assert client.post("/api/login/").status_code == 200
        assert BlockedSource.objects.count() == 0

    def test_a_blocked_person_signed_in_is_blocked_by_account(self):
        client = person()
        statuses(client, "/api/anything/", 120)
        statuses(client, "/api/anything/", 5)
        assert client.get("/api/anything/").status_code == 429
        assert person().get("/api/anything/").status_code == 200


class TestRealAddress:
    def test_changing_headers_does_not_skip_the_limit(self):
        client = visitor()
        for number in range(11):
            response = client.post(
                "/api/login/",
                HTTP_X_FORWARDED_FOR=f"198.51.100.{number}",
                HTTP_X_REAL_IP=f"198.51.100.{number}",
                HTTP_FORWARDED=f"for=198.51.100.{number}",
                HTTP_CLIENT_IP=f"198.51.100.{number}",
            )
        assert response.status_code == 429

    def test_behind_a_proxy_the_address_the_proxy_saw_is_counted(self, settings):
        settings.TRUSTED_PROXY_COUNT = 1
        proxy = visitor("10.0.0.2")  # every visitor arrives from the proxy

        def login_as(real, forged):
            return proxy.post("/api/login/", HTTP_X_FORWARDED_FOR=f"{forged}, {real}").status_code

        answers = [login_as("203.0.113.5", forged=f"9.9.9.{n}") for n in range(11)]
        assert answers == [200] * 10 + [429]  # made-up first entries changed nothing
        assert login_as("203.0.113.6", forged="9.9.9.9") == 200  # another real visitor is fine

    def test_addresses_are_not_stored_readably(self):
        visitor("203.0.113.9").post("/api/login/")
        keys = list(RateCounter.objects.values_list("key", flat=True))
        assert keys and all("203.0.113" not in key and len(key) == 64 for key in keys)


def test_old_counters_and_ended_blocks_can_be_cleared(clock):
    client = visitor()
    statuses(client, "/api/login/", 15)
    assert RateCounter.objects.count() and BlockedSource.objects.count()
    clock.advance(days=1)
    rate_limits.purge_old_counters()
    assert RateCounter.objects.count() == 0 and BlockedSource.objects.count() == 0
