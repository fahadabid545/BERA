import json

import pytest
from django.test import RequestFactory

from core import views

pytestmark = [pytest.mark.urls("core.tests.urls_for_tests"), pytest.mark.django_db]


def test_forced_error_shows_friendly_message_and_the_log_has_the_same_reference(
    client, project_log
):
    response = client.post("/api/boom/", {"x": 1}, content_type="application/json")

    error = response.json()["error"]
    assert response.status_code == 500
    assert error["message"] == "Something went wrong."
    reference = error["reference"]
    assert response["X-Request-ID"] == reference
    log = project_log.getvalue()
    assert f"request={reference}" in log
    assert "RuntimeError" in log


def test_no_internal_details_reach_the_user(client, project_log):
    response = client.post("/api/boom/", {"x": 1}, content_type="application/json")

    body = response.content.decode()
    assert "RuntimeError" not in body
    assert "secret_path" not in body
    assert "Traceback" not in body


def test_password_and_token_sent_in_a_request_are_not_written_to_the_log(client, project_log):
    client.post(
        "/api/boom/?token=query-token-999",
        json.dumps({"password": "Sup3r-Secret-Password", "token": "body-token-123"}),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer header-token-456",
    )

    log = project_log.getvalue()
    assert "RuntimeError" in log  # the failure itself was logged
    for secret in (
        "Sup3r-Secret-Password",
        "body-token-123",
        "header-token-456",
        "query-token-999",
    ):
        assert secret not in log


def test_form_mistake_names_the_field_and_adds_no_reference(client):
    response = client.post("/api/form/", {}, content_type="application/json")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["fields"] == {"email": "Enter a valid email address."}
    assert "reference" not in error


def test_every_response_carries_a_different_request_reference(client):
    first = client.get("/api/missing/")["X-Request-ID"]
    second = client.get("/api/missing/")["X-Request-ID"]
    assert first != second and len(first) == 8


def test_unknown_address_answers_in_the_shared_shape(client):
    response = client.get("/api/missing/")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not found."}}


def test_server_error_page_outside_the_api_is_friendly_and_has_a_reference():
    response = views.server_error(RequestFactory().get("/anything"))

    error = json.loads(response.content)["error"]
    assert response.status_code == 500
    assert error["message"] == "Something went wrong."
    assert len(error["reference"]) == 8
