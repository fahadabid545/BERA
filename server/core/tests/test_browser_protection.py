"""Headers, cookies and cross-site rules on the API's responses."""

import pytest
from django.conf import settings as django_settings
from rest_framework.test import APIClient

from core.tests.factories import make_admin_user
from signin import service
from signin.cookies import CSRF_COOKIE, refresh_cookie_name

ALLOWED = "http://localhost:3000"  # the development web app (see config/settings/development.py)
STRANGER = "https://evil.example.net"
EVERY_RESPONSE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


def admin_client_with_cookies():
    user = make_admin_user()
    issued = service.start_session(user_id=user.id, role="super", company_id=None, kind="admin")
    client = APIClient()
    client.cookies[refresh_cookie_name("admin")] = issued.refresh_token
    client.cookies[CSRF_COOKIE] = "csrf-value"
    return client


def assert_protected(response):
    for name, value in EVERY_RESPONSE_HEADERS.items():
        assert response[name] == value, name
    assert "camera=()" in response["Permissions-Policy"]


@pytest.mark.django_db
class TestHeadersOnEveryResponse:
    def test_a_normal_answer(self):
        response = APIClient().get("/api/health/")
        assert response.status_code == 200
        assert_protected(response)

    def test_an_unknown_address(self):
        response = APIClient().get("/api/nothing-here/")
        assert response.status_code == 404
        assert_protected(response)

    def test_a_refused_sign_in(self):
        response = APIClient().post("/api/auth/company/refresh/")
        assert response.status_code == 401
        assert_protected(response)

    def test_a_too_large_request(self):
        response = APIClient().post(
            "/api/auth/company/refresh/", "x" * 300_000, content_type="application/json"
        )
        assert response.status_code == 413
        assert_protected(response)

    def test_a_cross_site_refusal(self):
        response = APIClient().get("/api/health/", HTTP_ORIGIN=STRANGER)
        assert response.status_code == 403
        assert_protected(response)

    def test_an_answer_from_a_wrong_method(self):
        response = APIClient().get("/api/auth/company/refresh/")
        assert response.status_code == 405
        assert_protected(response)


@pytest.mark.django_db
class TestCrossSiteRequests:
    def test_requests_without_an_origin_are_not_affected(self):
        assert APIClient().get("/api/health/").status_code == 200

    def test_the_own_web_app_is_allowed_and_may_read_the_answer(self):
        response = APIClient().get("/api/health/", HTTP_ORIGIN=ALLOWED)
        assert response.status_code == 200
        assert response["Access-Control-Allow-Origin"] == ALLOWED
        assert response["Access-Control-Allow-Credentials"] == "true"
        assert response["Vary"] == "Origin"

    def test_the_servers_own_address_is_allowed(self):
        response = APIClient().get("/api/health/", HTTP_ORIGIN="http://testserver")
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "origin",
        [
            STRANGER,
            "null",
            "http://localhost:3001",
            "https://localhost:3000",
            "http://localhost:3000.evil.example.net",
            "http://evil.example.net/http://localhost:3000",
            "",
        ],
    )
    def test_other_sites_are_refused_and_told_nothing(self, origin):
        response = APIClient().get("/api/health/", HTTP_ORIGIN=origin)
        assert response.status_code == 403
        assert response.json() == {
            "error": {"code": "not_allowed", "message": "You do not have permission to do this."}
        }
        assert "Access-Control-Allow-Origin" not in response
        assert "Access-Control-Allow-Credentials" not in response

    def test_a_forged_refresh_from_another_site_is_refused_even_with_valid_cookies(self):
        client = admin_client_with_cookies()
        response = client.post(
            "/api/auth/admin/refresh/", HTTP_ORIGIN=STRANGER, HTTP_X_CSRF_TOKEN="csrf-value"
        )
        assert response.status_code == 403
        # Nothing was used up: the real refresh token still works from the real site.
        again = client.post(
            "/api/auth/admin/refresh/", HTTP_ORIGIN=ALLOWED, HTTP_X_CSRF_TOKEN="csrf-value"
        )
        assert again.status_code == 200

    def test_the_preflight_check_of_the_own_web_app_is_answered(self):
        response = APIClient().options(
            "/api/auth/company/refresh/",
            HTTP_ORIGIN=ALLOWED,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        assert response.status_code == 204
        assert response["Access-Control-Allow-Origin"] == ALLOWED
        assert "X-CSRF-Token" in response["Access-Control-Allow-Headers"]
        assert "PATCH" in response["Access-Control-Allow-Methods"]
        assert_protected(response)

    def test_the_preflight_check_of_another_site_is_refused(self):
        response = APIClient().options(
            "/api/auth/company/refresh/",
            HTTP_ORIGIN=STRANGER,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        assert response.status_code == 403
        assert "Access-Control-Allow-Methods" not in response


@pytest.mark.django_db
class TestCookies:
    def renew(self):
        client = admin_client_with_cookies()
        return client.post("/api/auth/admin/refresh/", HTTP_X_CSRF_TOKEN="csrf-value")

    def test_sign_in_cookies_are_protected_in_production_like_settings(self):
        assert django_settings.DEBUG is False
        response = self.renew()
        assert_protected(response)
        for name in ("bera_admin_access", "bera_admin_refresh"):
            cookie = response.cookies[name]
            assert cookie["httponly"] is True  # page scripts cannot read it
            assert cookie["secure"] is True  # only over https
            assert cookie["samesite"] == "Strict"  # not sent from other sites
        # The one cookie scripts must read is still never sent from other sites.
        assert response.cookies[CSRF_COOKIE]["samesite"] == "Strict"
        assert response.cookies[CSRF_COOKIE]["secure"] is True

    def test_only_local_development_over_http_drops_the_secure_flag(self, settings):
        settings.DEBUG = True
        response = self.renew()
        for name in ("bera_admin_access", "bera_admin_refresh", CSRF_COOKIE):
            assert response.cookies[name]["secure"] == ""
            assert response.cookies[name]["samesite"] == "Strict"
        assert response.cookies["bera_admin_access"]["httponly"] is True
