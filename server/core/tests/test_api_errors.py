import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ParseError, ValidationError
from rest_framework.test import APIRequestFactory

from core.errors import AppError
from core.permissions import PublicAccess


def call(exception):
    @api_view(["GET"])
    @permission_classes([PublicAccess])
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


def test_validation_error_names_the_wrong_field():
    response = call(ValidationError({"name": ["This field is required."]}))
    assert response.status_code == 400
    assert response.data == {
        "error": {
            "code": "validation_error",
            "message": "Please check the form and try again.",
            "fields": {"name": "This field is required."},
        }
    }


def test_validation_error_flattens_nested_fields_and_general_messages():
    nested = ValidationError({"items": [{}, {"name": ["Too long."]}], "non_field_errors": ["Bad."]})
    error = call(nested).data["error"]
    assert error["fields"] == {"items.1.name": "Too long."}
    assert error["message"] == "Bad."


def test_unreadable_request_gets_a_plain_message():
    response = call(ParseError("JSON parse error - Expecting value: line 1 column 1 (char 0)"))
    assert response.data["error"] == {
        "code": "bad_request",
        "message": "The request could not be read.",
    }


def test_django_not_found_and_permission_errors_use_the_shared_shape():
    assert call(Http404("no such row in table x")).data["error"]["code"] == "not_found"
    assert call(PermissionDenied("internal reason")).data["error"]["code"] == "not_allowed"


def test_framework_error_keeps_its_status_and_code():
    response = call(NotFound())
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_unexpected_error_hides_internals_and_gives_a_reference():
    response = call(RuntimeError("password=hunter2 in /srv/secret/path"))
    error = response.data["error"]
    assert response.status_code == 500
    assert error["code"] == "internal_error"
    assert error["message"] == "Something went wrong."
    assert len(error["reference"]) == 8
    assert "hunter2" not in str(response.data) and "/srv" not in str(response.data)


@pytest.mark.django_db
def test_health_endpoint_reports_ok(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
