"""The public health address is watched by an outside service, so anyone can read it. It says
OK or not OK, and nothing else."""

import re

import pytest
from django.db import OperationalError
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_the_answer_when_all_is_well_is_only_ok():
    response = APIClient().get("/api/health/")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_the_headers_announce_no_software_or_version():
    response = APIClient().get("/api/health/")
    for name in ("Server", "X-Powered-By", "X-Version"):
        assert name not in response
    assert not re.search(r"\d+\.\d+", str(dict(response.items())))


def test_when_the_database_is_down_it_says_only_that_it_is_not_available(monkeypatch):
    def fail():
        raise OperationalError("connection to 10.0.0.5 as bera_app refused")

    monkeypatch.setattr("core.views.connection.ensure_connection", fail)
    response = APIClient().get("/api/health/")
    body = response.content.decode()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
    for leaked in ("10.0.0.5", "bera_app", "database", "postgres", "Operational"):
        assert leaked.lower() not in body.lower()


def test_it_needs_no_account_and_is_not_limited():
    client = APIClient()
    assert all(client.get("/api/health/").status_code == 200 for _ in range(30))
