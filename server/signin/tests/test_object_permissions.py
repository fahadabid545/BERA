import uuid

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient

from companies.models import Company
from core.models import CompanyOwnedModel
from signin import service
from signin.service import RevokeReason
from signin.tests.models_for_tests import KINDS_OF_OBJECT

pytestmark = [pytest.mark.urls("signin.tests.urls_for_objects"), pytest.mark.django_db]
NOT_FOUND = {"error": {"code": "not_found", "message": "Not found."}}


@pytest.fixture(autouse=True)
def object_tables(db):
    with connection.schema_editor() as editor:
        for model in KINDS_OF_OBJECT.values():
            editor.create_model(model)


@pytest.fixture
def companies(db):
    owner = get_user_model().objects.get(id=1)
    return Company.objects.create(name="Mine Fake Ltd", owner=owner), Company.objects.create(
        name="Theirs Fake Ltd", owner=owner
    )


def sign_in(company, *, user_id=2, role="owner"):
    issued = service.start_session(
        user_id=user_id, role=role, company_id=company.id, kind="company"
    )
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def route(model_name, *parts, prefix=""):
    return f"/api/{prefix}{model_name.lower()}s/" + "".join(f"{part}/" for part in parts)


@pytest.mark.parametrize("name", KINDS_OF_OBJECT)
def test_own_companys_object_is_reachable(companies, name):
    mine, _ = companies
    record = KINDS_OF_OBJECT[name].objects.create(company=mine)
    response = sign_in(mine).get(route(name, record.id))
    assert response.status_code == 200
    assert response.json()["id"] == str(record.id)


@pytest.mark.parametrize("name", KINDS_OF_OBJECT)
def test_another_companys_object_looks_exactly_like_a_missing_one(companies, name):
    mine, theirs = companies
    others = KINDS_OF_OBJECT[name].objects.create(company=theirs)
    client = sign_in(mine)

    wrong_company = client.get(route(name, others.id))
    missing = client.get(route(name, uuid.uuid4()))

    assert wrong_company.status_code == missing.status_code == 404
    assert wrong_company.json() == missing.json() == NOT_FOUND


@pytest.mark.parametrize("name", KINDS_OF_OBJECT)
def test_another_companys_object_cannot_be_deleted_or_changed(companies, name):
    mine, theirs = companies
    others = KINDS_OF_OBJECT[name].objects.create(company=theirs)
    response = sign_in(mine).delete(route(name, others.id, "delete"))
    assert response.status_code == 404
    assert KINDS_OF_OBJECT[name].objects.filter(id=others.id).exists()


@pytest.mark.parametrize("name", KINDS_OF_OBJECT)
def test_the_own_company_can_delete_its_object(companies, name):
    mine, _ = companies
    record = KINDS_OF_OBJECT[name].objects.create(company=mine)
    assert sign_in(mine).delete(route(name, record.id, "delete")).status_code == 204


@pytest.mark.parametrize("name", KINDS_OF_OBJECT)
def test_lists_show_only_the_own_company(companies, name):
    mine, theirs = companies
    model = KINDS_OF_OBJECT[name]
    own = model.objects.create(company=mine)
    model.objects.create(company=theirs)
    ids = [item["id"] for item in sign_in(mine).get(route(name)).json()]
    assert ids == [str(own.id)]


@pytest.mark.parametrize(
    "guess", ["1", "2", "0", "-1", "../etc/passwd", "x' OR '1'='1", "%00", "null"]
)
def test_guessed_or_malformed_identifiers_are_simply_not_found(companies, guess):
    mine, _ = companies
    KINDS_OF_OBJECT["Project"].objects.create(company=mine)
    response = sign_in(mine).get(f"/api/projects/{guess}/")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND


def test_identifiers_are_random_and_not_counting_numbers(companies):
    mine, _ = companies
    model = KINDS_OF_OBJECT["Project"]
    first, second = model.objects.create(company=mine), model.objects.create(company=mine)
    for record in (first, second):
        assert isinstance(record.id, uuid.UUID) and record.id.version == 4
    assert first.id != second.id and abs(first.id.int - second.id.int) > 1000


def test_the_role_decides_after_the_company_has_been_checked(companies):
    mine, theirs = companies
    model = KINDS_OF_OBJECT["Project"]
    own, others = model.objects.create(company=mine), model.objects.create(company=theirs)
    member = sign_in(mine, user_id=3, role="member")
    owner = sign_in(mine, user_id=2, role="owner")

    refused = member.get(f"/api/owner-only-projects/{own.id}/")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "not_allowed")
    assert member.get("/api/owner-only-projects/").status_code == 403
    # Another company's record is "not found" even for a role that is not allowed anyway.
    assert member.get(f"/api/owner-only-projects/{others.id}/").json() == NOT_FOUND
    assert owner.get(f"/api/owner-only-projects/{own.id}/").status_code == 200


def test_an_admin_sign_in_does_not_open_company_data(companies):
    mine, _ = companies
    record = KINDS_OF_OBJECT["Project"].objects.create(company=mine)
    issued = service.start_session(user_id=4, role="super", company_id=None, kind="admin")
    client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
    assert client.get(route("Project", record.id)).status_code == 401


def test_a_blocked_person_loses_access_at_once_even_with_a_valid_token(companies):
    mine, _ = companies
    record = KINDS_OF_OBJECT["Project"].objects.create(company=mine)
    client = sign_in(mine, user_id=5)
    assert client.get(route("Project", record.id)).status_code == 200

    get_user_model().objects.filter(id=5).update(is_active=False)

    response = client.get(route("Project", record.id))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_signed_in"


def test_a_removed_person_loses_access_at_once(companies):
    mine, _ = companies
    record = KINDS_OF_OBJECT["Project"].objects.create(company=mine)
    client = sign_in(mine, user_id=6)
    get_user_model().objects.filter(id=6).delete()
    assert client.get(route("Project", record.id)).status_code == 401


def test_a_blocked_person_cannot_renew_their_tokens_either(companies):
    mine, _ = companies
    issued = service.start_session(user_id=5, role="owner", company_id=mine.id, kind="company")
    get_user_model().objects.filter(id=5).update(is_active=False)
    from rest_framework.exceptions import NotAuthenticated

    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.refresh_token, "company")


def test_revoked_sessions_lose_access_to_objects_at_once(companies):
    mine, _ = companies
    record = KINDS_OF_OBJECT["Project"].objects.create(company=mine)
    client = sign_in(mine, user_id=2)
    service.revoke_company_sessions(mine.id, RevokeReason.COMPANY_SUSPENDED)
    assert client.get(route("Project", record.id)).status_code == 401


def test_every_model_with_a_company_is_built_on_the_shared_base():
    outside_the_base = [
        model.__name__
        for model in apps.get_models()
        if any(field.name == "company" for field in model._meta.get_fields())
        and not issubclass(model, CompanyOwnedModel)
    ]
    assert outside_the_base == []
