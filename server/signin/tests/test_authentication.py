import pytest
from rest_framework.test import APIClient

from signin import service
from signin.cookies import CSRF_COOKIE, access_cookie_name
from signin.service import RevokeReason
from signin.tests.helpers import forge

pytestmark = [pytest.mark.urls("signin.tests.urls"), pytest.mark.django_db]

NOT_SIGNED_IN = {"code": "not_signed_in", "message": "You are not signed in."}


def bearer(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def company_sign_in():
    return service.start_session(user_id=7, role="owner", company_id=3, kind="company")


def admin_sign_in():
    return service.start_session(user_id=1, role="super", company_id=None, kind="admin")


def test_a_valid_token_opens_a_route_of_its_kind():
    response = APIClient().get("/api/company-only/", **bearer(company_sign_in().access_token))
    assert response.status_code == 200
    assert response.json() == {"user_id": 7, "role": "owner", "company_id": 3}


def test_company_and_admin_tokens_cannot_open_each_others_routes():
    client = APIClient()
    company, admin = company_sign_in(), admin_sign_in()
    assert client.get("/api/admin-only/", **bearer(company.access_token)).status_code == 401
    assert client.get("/api/company-only/", **bearer(admin.access_token)).status_code == 401
    assert client.get("/api/admin-only/", **bearer(admin.access_token)).status_code == 200


def test_the_signed_in_person_is_named_in_the_log(project_log):
    token = company_sign_in().access_token
    APIClient().get("/api/log-something/", **bearer(token))
    line = next(line for line in project_log.getvalue().splitlines() if "doing the work" in line)
    assert "user=7 company=3" in line
    assert token not in project_log.getvalue()


@pytest.mark.parametrize(
    "credentials",
    [
        {},
        bearer("garbage"),
        bearer(""),
        {"HTTP_AUTHORIZATION": "Basic dXNlcjpwYXNz"},
        bearer(forge(secret="test-only-attackers-guess-long-enough-123")),
        bearer(forge(issued_ago=7200)),
        bearer(forge(aud="bera-admin")),
        bearer(forge()),  # correct shape and key, but no such session
    ],
    ids=[
        "missing",
        "garbage",
        "empty",
        "wrong scheme",
        "forged",
        "expired",
        "wrong audience",
        "no session",
    ],
)
def test_every_kind_of_bad_sign_in_gets_the_same_answer(credentials):
    response = APIClient().get("/api/company-only/", **credentials)
    assert response.status_code == 401
    assert response.json() == {"error": NOT_SIGNED_IN}


def test_a_token_in_the_address_is_ignored():
    token = company_sign_in().access_token
    response = APIClient().get(f"/api/company-only/?access_token={token}&token={token}")
    assert response.status_code == 401


def test_a_revoked_session_stops_working_at_once():
    issued = company_sign_in()
    client = APIClient()
    assert client.get("/api/company-only/", **bearer(issued.access_token)).status_code == 200
    service.revoke_company_sessions(3, RevokeReason.COMPANY_SUSPENDED)
    assert client.get("/api/company-only/", **bearer(issued.access_token)).status_code == 401


def cookie_client(issued, kind="company", csrf="csrf-value"):
    client = APIClient()
    client.cookies[access_cookie_name(kind)] = issued.access_token
    client.cookies[CSRF_COOKIE] = csrf
    return client


def test_the_sign_in_cookie_works_for_reading():
    assert cookie_client(company_sign_in()).get("/api/company-only/").status_code == 200


def test_changes_with_the_cookie_need_the_matching_csrf_header():
    client = cookie_client(company_sign_in())
    without = client.post("/api/company-only/")
    wrong = client.post("/api/company-only/", HTTP_X_CSRF_TOKEN="other-value")
    right = client.post("/api/company-only/", HTTP_X_CSRF_TOKEN="csrf-value")
    assert (without.status_code, wrong.status_code, right.status_code) == (403, 403, 200)
    assert without.json()["error"]["code"] == "not_allowed"


def test_changes_with_a_bearer_header_need_no_csrf_header():
    issued = company_sign_in()
    assert APIClient().post("/api/company-only/", **bearer(issued.access_token)).status_code == 200


def test_a_bad_cookie_is_refused_before_csrf_is_considered():
    client = APIClient()
    client.cookies[access_cookie_name("company")] = "garbage"
    assert client.post("/api/company-only/").status_code == 401
