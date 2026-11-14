"""A company can only ever see its own data: every kind, by every way of asking for it.

Each test signs in as company "mine" and tries to reach what belongs to company "theirs". The
answer must be exactly the answer for something that does not exist, and must never contain
anything of theirs. Run these again before launch with `python -m pytest -m isolation`.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from rest_framework.test import APIClient

from companies.models import Company, CompanyUser
from core.models import CompanyOwnedModel
from core.tests.factories import make_company_user, start_session_for
from signin.tests import models_for_tests
from signin.tests.helpers import forge
from signin.tests.models_for_tests import KINDS_OF_OBJECT

pytestmark = [
    pytest.mark.urls("signin.tests.urls_for_objects"),
    pytest.mark.django_db,
    pytest.mark.isolation,
]
NOT_FOUND = {"error": {"code": "not_found", "message": "Not found."}}
THEIRS_TITLE = "SECRET-OF-THE-OTHER-COMPANY"
MINE_TITLE = "mine-visible"

# Kinds of company data the isolation ticket names. Every one needs a stand-in kind above.
KINDS_NAMED_IN_THE_TICKET = {
    "Project",
    "Cv",
    "Result",
    "StoredFile",
    "UsageRecord",
    "Invoice",
    "Export",
    "SharedReport",
}
# Real company data models that have their own isolation tests (add a name here, with the
# tests, in the same change that adds the model).
# Invitation: companies/tests/test_invites.py (own company's list, resend and revoke only).
# ActivityEntry: activity/tests/test_activity_log.py (the list holds only the own company's).
# Subscription: plans/tests/test_subscription_states.py (companies are kept apart).
# LimitOverride: plans/tests/test_limits.py (read for one company only).
# Project: projects/tests/test_create_project.py (TestAnotherCompany).
# Requirement: projects/tests/test_requirement_editor.py (TestAnotherCompany).
# ProjectScoringSettings: projects/tests/test_scoring_settings.py (TestAnotherCompany).
# CvFile: cvs/tests/test_cv_upload.py (TestAnotherCompany).
# ProcessingTurn: cvs/tests/test_processing.py (fairness and TestJobsRunForTheRightCompany).
# CvProfile, CvContact: cvs/tests/test_ai_reading.py (TestAnotherCompany).
# Candidate: cvs/tests/test_candidate_record.py (TestAnotherCompany).
# RequirementResult: cvs/tests/test_requirement_evaluation.py (TestAnotherCompany).
# AtsScore: cvs/tests/test_ats_score.py (TestAnotherCompany).
# ExtraFactorValues: cvs/tests/test_extra_factors.py (TestAnotherCompany).
# ProjectFactorSettings: projects/tests/test_factor_settings.py (TestAnotherCompany).
# UsagePeriod, UsageCounter, CvUsage: usage/tests/test_usage_counting.py (kept apart per company).
REAL_MODELS_WITH_ISOLATION_TESTS: set[str] = {
    "Invitation",
    "ActivityEntry",
    "Subscription",
    "LimitOverride",
    "UsagePeriod",
    "UsageCounter",
    "CvUsage",
    "Project",
    "Requirement",
    "ProjectScoringSettings",
    "CvFile",
    "ProcessingTurn",
    "CvProfile",
    "CvContact",
    "Candidate",
    "RequirementResult",
    "AtsScore",
    "AiCall",
    "CandidateScore",
    "ExtraFactorValues",
    "ProjectFactorSettings",
}


@pytest.fixture(autouse=True)
def object_tables(db):
    with connection.schema_editor() as editor:
        for model in KINDS_OF_OBJECT.values():
            editor.create_model(model)


@pytest.fixture
def companies(db):
    return Company.objects.create(name="Mine Fake Ltd"), Company.objects.create(
        name="Theirs Fake Ltd"
    )


def client_of(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def address(name, *parts):
    return f"/api/{name.lower()}s/" + "".join(f"{part}/" for part in parts)


def make(name, company, title):
    return KINDS_OF_OBJECT[name].objects.create(company=company, title=title)


def leaks_nothing_of_theirs(response, theirs_record):
    text = response.content.decode()
    return THEIRS_TITLE not in text and str(theirs_record.id) not in text


KINDS = sorted(KINDS_OF_OBJECT)


class TestTheSuiteCoversEveryKind:
    def test_every_kind_the_ticket_names_has_a_stand_in(self):
        assert KINDS_NAMED_IN_THE_TICKET <= set(KINDS_OF_OBJECT)

    def test_every_real_company_data_model_has_isolation_tests(self):
        real = {
            model.__name__
            for model in apps.get_models()
            if issubclass(model, CompanyOwnedModel)
            and not model._meta.abstract
            and model.__module__ != models_for_tests.__name__
        }
        missing = real - REAL_MODELS_WITH_ISOLATION_TESTS
        assert not missing, (
            f"New company data without isolation tests: {sorted(missing)}. Add tests that "
            "try to reach another company's records for each, then list the model here."
        )


@pytest.mark.parametrize("name", KINDS)
class TestAnotherCompanysRecord:
    def test_looking_at_it_looks_exactly_like_looking_for_nothing(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        client = client_of(mine)
        response = client.get(address(name, record.id))
        missing = client.get(address(name, uuid.uuid4()))
        assert response.status_code == missing.status_code == 404
        assert response.json() == missing.json() == NOT_FOUND

    def test_it_is_not_in_lists_or_live_updates(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        make(name, mine, MINE_TITLE)
        client = client_of(mine)
        for suffix in ((), ("live",)):
            response = client.get(address(name, *suffix))
            assert response.status_code == 200
            assert [item["title"] for item in response.json()] == [MINE_TITLE]
            assert leaks_nothing_of_theirs(response, record)

    def test_searching_never_finds_it(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        client = client_of(mine)
        for query in (THEIRS_TITLE, "SECRET", "", "%", "_", "' OR 1=1 --"):
            response = client.get(address(name, "search"), {"q": query})
            assert response.status_code == 200
            assert leaks_nothing_of_theirs(response, record), query

    def test_its_download_or_export_link_does_not_work(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        response = client_of(mine).get(address(name, record.id, "download"))
        assert response.status_code == 404 and response.json() == NOT_FOUND

    def test_it_cannot_be_changed_or_deleted(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        client = client_of(mine)
        changed = client.patch(
            address(name, record.id, "edit"), {"title": "hijacked"}, format="json"
        )
        deleted = client.delete(address(name, record.id, "delete"))
        assert changed.status_code == deleted.status_code == 404
        record.refresh_from_db()
        assert record.title == THEIRS_TITLE and record.company_id == theirs.pk

    def test_asking_for_it_by_company_in_the_address_changes_nothing(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        client = client_of(mine)
        for parameter in ("company", "company_id", "company__id", "owner"):
            response = client.get(address(name), {parameter: theirs.pk})
            assert leaks_nothing_of_theirs(response, record), parameter

    def test_its_identifier_does_not_open_any_other_kind_either(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        client = client_of(mine)
        for other in KINDS:
            assert client.get(address(other, record.id)).status_code == 404

    def test_the_own_record_still_works_by_every_route(self, companies, name):
        mine, _ = companies
        record = make(name, mine, MINE_TITLE)
        client = client_of(mine)
        assert client.get(address(name, record.id)).status_code == 200
        assert client.get(address(name, record.id, "download")).status_code == 200
        assert client.get(address(name, "search"), {"q": "mine"}).json()[0]["id"] == str(record.id)
        edit = client.patch(address(name, record.id, "edit"), {"title": "new"}, format="json")
        assert edit.status_code == 200

    def test_a_visitor_reaches_nothing_by_any_route(self, companies, name):
        _, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        visitor = APIClient()
        routes = [
            ("get", address(name)),
            ("get", address(name, "live")),
            ("get", address(name, "search")),
            ("get", address(name, record.id)),
            ("get", address(name, record.id, "download")),
            ("patch", address(name, record.id, "edit")),
            ("delete", address(name, record.id, "delete")),
        ]
        for method, route in routes:
            response = getattr(visitor, method)(route)
            assert response.status_code == 401, route
            assert leaks_nothing_of_theirs(response, record)

    def test_a_role_does_not_get_past_the_company_wall(self, companies, name):
        mine, theirs = companies
        record = make(name, theirs, THEIRS_TITLE)
        for role in ("owner", "member"):
            response = client_of(mine, role).get(address(name, record.id))
            assert response.status_code == 404, role


class TestPeople:
    """Company users, with the real model: the team list and a person's page."""

    def test_another_companys_person_looks_like_nobody(self, companies):
        mine, theirs = companies
        stranger = make_company_user(theirs, name=THEIRS_TITLE)
        client = client_of(mine)
        found = client.get(f"/api/users/{stranger.pk}/")
        guessed_missing = client.get("/api/users/999999/")
        assert found.status_code == guessed_missing.status_code == 404
        assert found.json() == guessed_missing.json() == NOT_FOUND

    def test_the_list_holds_only_the_own_company(self, companies):
        mine, theirs = companies
        stranger = make_company_user(theirs, name=THEIRS_TITLE)
        client = client_of(mine)
        response = client.get("/api/users/")
        assert response.status_code == 200
        assert THEIRS_TITLE not in response.content.decode()
        assert all(
            CompanyUser.objects.get(pk=item["id"]).company_id == mine.pk for item in response.json()
        )
        assert stranger.pk not in [item["id"] for item in response.json()]

    def test_counting_through_the_numbers_finds_nobody_of_another_company(self, companies):
        mine, theirs = companies
        make_company_user(theirs, name=THEIRS_TITLE)
        client = client_of(mine)
        reached = {
            number
            for number in range(1, CompanyUser.objects.latest("id").pk + 5)
            if client.get(f"/api/users/{number}/").status_code == 200
        }
        assert {CompanyUser.objects.get(pk=n).company_id for n in reached} == {mine.pk}


class TestSessionsCannotBeMovedToAnotherCompany:
    def test_a_token_naming_another_company_is_refused(self, companies):
        mine, theirs = companies
        person = make_company_user(mine, role="owner")
        issued = start_session_for(
            user_id=person.pk, role="owner", company_id=mine.pk, kind="company"
        )
        record = make("Project", theirs, THEIRS_TITLE)
        # Even a correctly signed token cannot name a company the session does not belong to.
        token = forge(sub=str(person.pk), sid=issued.session_id, cid=theirs.pk, role="owner")
        response = APIClient(HTTP_AUTHORIZATION=f"Bearer {token}").get(
            address("Project", record.id)
        )
        assert response.status_code == 401 and leaks_nothing_of_theirs(response, record)

    def test_a_person_moved_to_another_company_cannot_use_the_old_session_there(self, companies):
        mine, theirs = companies
        person = make_company_user(mine, role="member")
        issued = start_session_for(
            user_id=person.pk, role="member", company_id=mine.pk, kind="company"
        )
        record = make("Project", theirs, THEIRS_TITLE)
        CompanyUser.objects.filter(pk=person.pk).update(company=theirs)
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        assert client.get(address("Project", record.id)).status_code == 401

    def test_an_admin_sign_in_reaches_no_company_data(self, companies):
        _, theirs = companies
        record = make("Project", theirs, THEIRS_TITLE)
        admin = start_session_for(user_id=1, role="super", company_id=None, kind="admin")
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {admin.access_token}")
        assert client.get(address("Project", record.id)).status_code == 401
