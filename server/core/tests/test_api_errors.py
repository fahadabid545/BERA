import pytest
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory

from core.errors import AppError


def call(exception):
    @api_view(["GET"])
    def failing_view(request):
        raise exception

    return failing_view(APIRequestFactory().get("/"))


def test_app_error_uses_shared_shape():
    response = call(AppError("quota_exceeded", "Too many.", {"limit": 5}, 429))
    assert response.status_code == 429
    assert response.data == {
        "error": {"code": "quota_exceeded", "message": "Too many.", "details": {"limit": 5}}
    }


def test_app_error_without_details_omits_them():
    response = call(AppError("nope", "No."))
    assert response.data == {"error": {"code": "nope", "message": "No."}}


def test_validation_error_is_reported_with_field_details():
    response = call(ValidationError({"name": ["This field is required."]}))
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert "name" in response.data["error"]["details"]


def test_framework_error_keeps_its_status_and_code():
    response = call(NotFound())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_unexpected_error_hides_internals():
    response = call(RuntimeError("password=hunter2 in /srv/secret/path"))
    assert response.status_code == 500
    assert response.data == {
        "error": {"code": "internal_error", "message": "Something went wrong. Please try again."}
    }


@pytest.mark.django_db
def test_health_endpoint_reports_ok(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
