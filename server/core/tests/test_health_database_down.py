from django.db import OperationalError
from rest_framework.test import APIClient


def test_health_reports_unavailable_database(monkeypatch):
    def fail():
        raise OperationalError("connection to 10.0.0.5 refused")

    monkeypatch.setattr("core.views.connection.ensure_connection", fail)
    response = APIClient().get("/api/health/")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "10.0.0.5" not in response.content.decode()
