"""Limits on routes that exist in the real URL list."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_token_refresh_is_limited_to_30_a_minute_per_address():
    client = APIClient(REMOTE_ADDR="203.0.113.9")
    answers = [client.post("/api/auth/company/refresh/").status_code for _ in range(31)]
    assert answers == [401] * 30 + [429]  # the first 30 reach the sign-in check


def test_the_health_check_is_never_limited():
    client = APIClient(REMOTE_ADDR="203.0.113.9")
    assert {client.get("/api/health/").status_code for _ in range(130)} == {200}
