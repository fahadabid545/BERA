import pytest
from django.conf import settings
from rest_framework.test import APIClient

from signin import service
from signin.cookies import CSRF_COOKIE, access_cookie_name, refresh_cookie_name
from signin.models import Session
from signin.service import RevokeReason

pytestmark = pytest.mark.django_db
ROUTES = {"company": "/api/auth/company/refresh/", "admin": "/api/auth/admin/refresh/"}


def sign_in(kind="company"):
    if kind == "company":
        return service.start_session(user_id=7, role="owner", company_id=3, kind="company")
    return service.start_session(user_id=1, role="super", company_id=None, kind="admin")


def client_with(refresh_token, kind="company", csrf="csrf-value"):
    client = APIClient()
    client.cookies[refresh_cookie_name(kind)] = refresh_token
    client.cookies[CSRF_COOKIE] = csrf
    return client


def refresh(client, kind="company", csrf="csrf-value"):
    return client.post(ROUTES[kind], HTTP_X_CSRF_TOKEN=csrf)


@pytest.mark.parametrize("kind", ["company", "admin"])
def test_refreshing_sets_new_protected_cookies_and_returns_no_tokens(kind):
    issued = sign_in(kind)
    response = refresh(client_with(issued.refresh_token, kind), kind)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    access, new_refresh = (
        response.cookies[access_cookie_name(kind)],
        response.cookies[refresh_cookie_name(kind)],
    )
    assert access.value != issued.access_token and new_refresh.value != issued.refresh_token
    assert issued.access_token not in response.content.decode()
    for cookie in (access, new_refresh):
        assert cookie["httponly"] is True
        assert cookie["samesite"] == "Strict"
        assert cookie["secure"] is True
    assert new_refresh["path"] == f"/api/auth/{kind}/"
    assert access["path"] == "/api/"
    assert int(access["max-age"]) == 15 * 60
    assert int(new_refresh["max-age"]) == 7 * 24 * 60 * 60
    assert response.cookies[CSRF_COOKIE]["httponly"] == ""  # scripts read this one on purpose


def test_cookies_are_not_marked_secure_only_in_local_development(settings):
    settings.DEBUG = True
    issued = sign_in()
    response = refresh(client_with(issued.refresh_token))
    assert response.cookies[access_cookie_name("company")]["secure"] == ""
    assert response.cookies[access_cookie_name("company")]["httponly"] is True


def test_the_old_refresh_token_does_not_work_a_second_time_and_ends_the_session():
    issued = sign_in()
    assert refresh(client_with(issued.refresh_token)).status_code == 200
    replay = refresh(client_with(issued.refresh_token))
    assert replay.status_code == 401
    assert Session.objects.get().revoke_reason == RevokeReason.REFRESH_REUSE


@pytest.mark.parametrize("kind", ["company", "admin"])
def test_a_refresh_token_of_the_other_kind_is_refused(kind):
    other = "admin" if kind == "company" else "company"
    issued = sign_in(other)
    client = client_with(issued.refresh_token, kind)  # placed in this kind's cookie
    assert refresh(client, kind).status_code == 401


def test_without_a_refresh_cookie_the_answer_is_not_signed_in():
    response = APIClient().post(ROUTES["company"])
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_signed_in"


def test_a_tampered_refresh_token_gets_the_same_answer():
    issued = sign_in()
    response = refresh(client_with(issued.refresh_token + "x"))
    assert response.status_code == 401
    assert response.json()["error"] == APIClient().post(ROUTES["company"]).json()["error"]


def test_refreshing_needs_the_csrf_header():
    issued = sign_in()
    client = client_with(issued.refresh_token)
    assert client.post(ROUTES["company"]).status_code == 403
    assert client.post(ROUTES["company"], HTTP_X_CSRF_TOKEN="other").status_code == 403
    assert Session.objects.get().status == Session.Status.ACTIVE  # nothing was used up


def test_refreshing_only_accepts_post():
    assert APIClient().get(ROUTES["company"]).status_code == 405


def test_tokens_are_not_logged_by_the_refresh_view(caplog):
    issued = sign_in()
    refresh(client_with(issued.refresh_token))
    refresh(client_with(issued.refresh_token))  # the replay is logged
    output = " ".join(f"{record.getMessage()} {record.args}" for record in caplog.records)
    assert issued.refresh_token not in output and issued.access_token not in output


def test_the_session_cookie_settings_do_not_depend_on_this_test():
    assert settings.DEBUG is False  # tests run with the production-like default
