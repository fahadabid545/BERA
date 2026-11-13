import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.errors import AppError
from core.tests.factories import make_company, make_company_user, start_session_for
from plans import subscriptions as subs
from plans.models import Plan
from projects import requirements as editor
from projects.models import Project, Requirement
from projects.requirements import near_duplicates, require_requirements_for_scoring

pytestmark = pytest.mark.django_db


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    plan = Plan.objects.create(
        name="Basic",
        status="active",
        price_usd=10,
        cvs_per_month=100,
        cvs_per_project=50,
        max_projects=5,
        max_team_accounts=3,
        max_top_n=10,
        monthly_ai_token_cap=10000,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def signed_in(company):
    return sign_in(company)


@pytest.fixture
def client(signed_in):
    return signed_in[1]


@pytest.fixture
def project(company, signed_in):
    return Project.objects.create(
        company=company,
        title="Backend engineer",
        job_description="text",
        reading_model="m",
        prompt_version="p",
        created_by=signed_in[0],
    )


def url(project):
    return f"/api/company/projects/{project.pk}/requirements/"


def item(text, kind="must", weight=None, **extra):
    body = {"kind": kind, "text": text, **extra}
    if weight is not None:
        body["weight"] = weight
    return body


def save(client, project, *items, **extra):
    return client.put(url(project), {"requirements": list(items), **extra}, format="json")


class TestSaving:
    def test_adds_requirements_in_the_order_given(self, client, project):
        response = save(client, project, item("Python"), item("Django", "nice", 2), item("SQL"))
        assert response.status_code == 200
        rows = response.json()["requirements"]
        assert [(row["text"], row["kind"], row["weight"]) for row in rows] == [
            ("Python", "must", 3),
            ("Django", "nice", 2),
            ("SQL", "must", 3),
        ]
        assert [row["text"] for row in client.get(url(project)).json()["requirements"]] == [
            "Python",
            "Django",
            "SQL",
        ]

    def test_the_default_weight_is_three(self, client, project):
        rows = save(client, project, item("Python")).json()["requirements"]
        assert rows[0]["weight"] == 3

    def test_editing_keeps_the_same_requirement(self, client, project):
        first = save(client, project, item("Python")).json()["requirements"][0]
        second = save(client, project, item("Python 3", "nice", 5, id=first["id"])).json()[
            "requirements"
        ][0]
        assert second["id"] == first["id"]
        assert (second["text"], second["kind"], second["weight"]) == ("Python 3", "nice", 5)
        assert Requirement.objects.filter(project=project).count() == 1

    def test_reordering_changes_the_order_only(self, client, project):
        rows = save(client, project, item("A"), item("B"), item("C")).json()["requirements"]
        reordered = [item(r["text"], r["kind"], r["weight"], id=r["id"]) for r in reversed(rows)]
        again = save(client, project, *reordered).json()["requirements"]
        assert [r["text"] for r in again] == ["C", "B", "A"]
        assert {r["id"] for r in again} == {r["id"] for r in rows}

    def test_removing_leaves_the_others(self, client, project):
        rows = save(client, project, item("A"), item("B")).json()["requirements"]
        save(client, project, item("B", id=rows[1]["id"]))
        assert list(Requirement.objects.filter(project=project).values_list("text", flat=True)) == [
            "B"
        ]

    def test_an_empty_list_clears_everything(self, client, project):
        save(client, project, item("A"))
        assert save(client, project).json()["requirements"] == []

    def test_a_member_may_edit(self, company, project):
        _, member = sign_in(company, role="member")
        assert save(member, project, item("A")).status_code == 200

    def test_saving_updates_the_projects_last_updated(self, client, project):
        before = Project.objects.get(pk=project.pk).updated_at
        save(client, project, item("A"))
        assert Project.objects.get(pk=project.pk).updated_at > before


class TestLimits:
    def test_thirty_are_allowed_and_thirty_one_are_not(self, client, project):
        assert save(client, project, *[item(f"Skill {n}") for n in range(30)]).status_code == 200
        response = save(client, project, *[item(f"Skill {n}") for n in range(31)])
        assert response.status_code == 400
        assert "requirements" in response.json()["error"]["fields"]
        assert Requirement.objects.filter(project=project).count() == 30

    @pytest.mark.parametrize("weight", [0, 6, -1, "x", 2.5])
    def test_weight_must_be_from_one_to_five(self, client, project, weight):
        assert save(client, project, item("A", weight=weight)).status_code == 400

    @pytest.mark.parametrize("weight", [1, 5])
    def test_the_ends_of_the_range_are_allowed(self, client, project, weight):
        assert save(client, project, item("A", weight=weight)).status_code == 200

    def test_text_is_required_and_limited_to_120_characters(self, client, project):
        assert save(client, project, item("a" * 120)).status_code == 200
        assert save(client, project, item("a" * 121)).status_code == 400
        assert save(client, project, item("  ")).status_code == 400

    def test_the_kind_must_be_known(self, client, project):
        assert save(client, project, item("A", kind="maybe")).status_code == 400

    def test_unknown_fields_are_refused(self, client, project):
        assert save(client, project, item("A", colour="red")).status_code == 400

    def test_a_requirement_of_another_project_cannot_be_claimed(self, company, client, project):
        other = Project.objects.create(
            company=company,
            title="O",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=project.created_by,
        )
        theirs = Requirement.objects.create(
            company=company, project=other, position=0, kind="must", text="Theirs", weight=3
        )
        response = save(client, project, item("Stolen", id=str(theirs.id)))
        assert response.status_code == 400
        theirs.refresh_from_db()
        assert theirs.text == "Theirs"

    def test_the_limits_come_from_platform_settings(self, client, project):
        from platform_settings.models import PlatformSetting
        from platform_settings.service import clear_cache

        PlatformSetting.objects.create(key="requirements.max_total", value=2)
        clear_cache()
        assert save(client, project, item("A"), item("B"), item("C")).status_code == 400


class TestNearDuplicates:
    def test_a_repeat_is_flagged_but_saved(self, client, project):
        response = save(client, project, item("5 years of Python"), item("5 years of python"))
        assert response.status_code == 200
        assert [w["code"] for w in response.json()["warnings"]] == ["near_duplicate"]
        assert Requirement.objects.filter(project=project).count() == 2

    def test_small_wording_differences_are_flagged(self):
        pairs = near_duplicates([item("Experience with Python"), item("Experience in Python")])
        assert len(pairs) == 1

    def test_different_requirements_are_not(self):
        assert near_duplicates([item("Python"), item("Project management")]) == []

    def test_punctuation_and_spacing_do_not_hide_a_repeat(self):
        assert len(near_duplicates([item("Python,  Django!"), item("python django")])) == 1

    def test_reading_the_list_shows_the_flags_too(self, client, project):
        save(client, project, item("Team player"), item("Team player"))
        assert len(client.get(url(project)).json()["warnings"]) == 1


class TestRescoringNotice:
    @pytest.fixture
    def scored(self, monkeypatch):
        monkeypatch.setattr(
            editor,
            "rescoring_estimate",
            lambda project: {"cvs": 12, "estimated_cost": __import__("decimal").Decimal("0.84")},
        )

    def test_no_notice_when_nothing_was_scored(self, client, project):
        assert save(client, project, item("A")).status_code == 200

    def test_a_change_after_scoring_asks_first_with_the_count_and_cost(
        self, client, project, scored
    ):
        response = save(client, project, item("A"))
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "rescoring_needed"
        assert error["details"] == {"cvs": 12, "estimated_cost": "0.840000"}
        assert not Requirement.objects.filter(project=project).exists()

    def test_confirming_saves_it(self, client, project, scored):
        response = save(client, project, item("A"), acknowledge_rescoring=True)
        assert response.status_code == 200
        assert Requirement.objects.filter(project=project).count() == 1

    def test_saving_without_a_change_needs_no_notice(self, client, project):
        rows = save(client, project, item("A", weight=4)).json()["requirements"]
        from unittest.mock import patch

        with patch.object(
            editor, "rescoring_estimate", return_value={"cvs": 9, "estimated_cost": 0}
        ):
            again = save(client, project, item("A", weight=4, id=rows[0]["id"]))
        assert again.status_code == 200

    def test_only_reordering_needs_no_notice(self, client, project):
        rows = save(client, project, item("A"), item("B")).json()["requirements"]
        from unittest.mock import patch

        swapped = [item(r["text"], weight=r["weight"], id=r["id"]) for r in reversed(rows)]
        with patch.object(
            editor, "rescoring_estimate", return_value={"cvs": 9, "estimated_cost": 0}
        ):
            assert save(client, project, *swapped).status_code == 200

    def test_a_changed_weight_does_need_it(self, client, project):
        rows = save(client, project, item("A", weight=3)).json()["requirements"]
        from decimal import Decimal
        from unittest.mock import patch

        with patch.object(
            editor, "rescoring_estimate", return_value={"cvs": 3, "estimated_cost": Decimal(1)}
        ):
            response = save(client, project, item("A", weight=4, id=rows[0]["id"]))
        assert response.status_code == 409


class TestBeforeScoring:
    def test_scoring_needs_at_least_one_requirement(self, project):
        with pytest.raises(AppError) as caught:
            require_requirements_for_scoring(project)
        assert caught.value.code == "requirements_needed"

    def test_one_is_enough(self, client, project):
        save(client, project, item("A"))
        require_requirements_for_scoring(project)


class TestAccess:
    def test_an_archived_project_is_read_only(self, client, project):
        save(client, project, item("A"))
        Project.objects.filter(pk=project.pk).update(status="archived")
        assert client.get(url(project)).status_code == 200
        response = save(client, project, item("B"))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "project_archived"
        assert Requirement.objects.get(project=project).text == "A"

    def test_nobody_signed_in_is_refused(self, project):
        assert APIClient().get(url(project)).status_code == 401


class TestAnotherCompany:
    def test_another_companys_requirements_cannot_be_read_or_changed(self, client):
        stranger = make_company()
        theirs = Project.objects.create(
            company=stranger,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=make_company_user(stranger),
        )
        Requirement.objects.create(
            company=stranger, project=theirs, position=0, kind="must", text="Theirs", weight=3
        )
        assert client.get(url(theirs)).status_code == 404
        assert save(client, theirs, item("Mine")).status_code == 404
        assert Requirement.objects.get(project=theirs).text == "Theirs"

    def test_a_requirement_always_belongs_to_the_projects_company(self, company, client, project):
        save(client, project, item("A"))
        assert Requirement.objects.get(project=project).company_id == company.pk
