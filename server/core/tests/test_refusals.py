import pytest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory

from companies.models import Company
from core.permissions import PublicAccess
from core.scoping import get_in_company

pytestmark = pytest.mark.urls("core.tests.urls_for_protection")


def error_of(response):
    body = response.json() if hasattr(response, "json") else response.data
    return response.status_code, body["error"]


def test_a_private_route_refuses_visitors_with_not_signed_in():
    status, error = error_of(APIClient().get("/api/private/"))
    assert status == 401
    assert error == {"code": "not_signed_in", "message": "You are not signed in."}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"HTTP_AUTHORIZATION": "Bearer not-a-real-token"},
        {"HTTP_AUTHORIZATION": "Bearer "},
        {"HTTP_COOKIE": "access_token=expired"},
    ],
    ids=["missing", "invalid", "empty", "cookie"],
)
def test_missing_and_invalid_sign_ins_get_the_same_answer(headers):
    missing = error_of(APIClient().get("/api/private/"))
    assert error_of(APIClient().get("/api/private/", **headers)) == missing


def record_lookup_view(company_id):
    """A signed-in user of the given company asking for a company record by number."""

    @api_view(["GET"])
    @permission_classes([PublicAccess])
    def view(request, record_id):
        record = get_in_company(Company.objects.all(), company_id, company_field="id", id=record_id)
        return Response({"id": record.id})

    return view


@pytest.fixture
def two_companies(db):
    return (
        Company.objects.create(name="First Fake Ltd"),
        Company.objects.create(name="Second Fake Ltd"),
    )


def ask(view, record_id):
    return error_of(view(APIRequestFactory().get("/"), record_id=record_id))


def test_a_record_of_another_company_looks_the_same_as_a_missing_one(two_companies):
    mine, other = two_companies
    view = record_lookup_view(mine.id)

    missing = ask(view, 999999)
    another_companys = ask(view, other.id)

    assert missing[0] == 404
    assert another_companys == missing
    assert missing[1] == {"code": "not_found", "message": "Not found."}


def test_a_record_of_the_own_company_is_found(two_companies):
    mine, _ = two_companies
    response = record_lookup_view(mine.id)(APIRequestFactory().get("/"), record_id=mine.id)
    assert response.status_code == 200


@pytest.mark.parametrize("address", ["/nothing-here/", "/api/nothing-here/", "/admin/", "/.env"])
def test_unknown_addresses_say_only_not_found(address):
    response = APIClient().get(address)
    body = response.content.decode()
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not found."}}
    for revealing in ("Traceback", "Django", "urlpatterns", "DEBUG", ".py"):
        assert revealing not in body
