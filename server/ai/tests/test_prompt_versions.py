import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ai.default_prompts import CV_READING_PROMPT
from ai.models import PromptVersion
from audit.models import AuditEvent
from core.tests.factories import make_admin_user, make_company, make_company_user
from platform_settings.service import get_setting
from projects.models import Project
from projects.service import create_project
from signin import service

pytestmark = pytest.mark.django_db
URL = "/api/admin/ai/prompts/"
REASON = "A test reason."


def admin_client(role="super"):
    admin = make_admin_user(role=role)
    issued = service.start_session(user_id=admin.pk, role=role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def boss():
    return admin_client("super")


def make_project(company=None, **fields):
    company = company or make_company()
    return Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model="m",
        created_by=make_company_user(company),
        **fields,
    )


def new_version(boss, kind="reading", text="New instructions."):
    return boss.post(URL, {"kind": kind, "text": text}, format="json")


def make_current(boss, kind, number, reason=REASON):
    return boss.put(
        f"{URL}current/", {"kind": kind, "number": number, "reason": reason}, format="json"
    )


def kinds_logged():
    return list(AuditEvent.objects.filter(kind__startswith="admin.").values_list("kind", flat=True))


class TestStartingPoint:
    def test_each_kind_starts_with_version_one_which_is_current(self, boss):
        data = boss.get(URL).json()
        assert [v["number"] for v in data["reading"]] == [1]
        assert [v["number"] for v in data["scoring"]] == [1]
        assert data["reading"][0]["text"] == CV_READING_PROMPT
        assert data["reading"][0]["current"] is True

    def test_a_project_pins_the_current_versions_when_it_is_created(self):
        project = make_project()
        assert (project.reading_prompt_version, project.scoring_prompt_version) == (1, 1)


class TestOnlySuperAdminsMayUseIt:
    def test_support_is_refused_everywhere(self):
        support = admin_client("support")
        project = make_project()
        assert support.get(URL).status_code == 403
        assert support.post(URL, {"kind": "reading", "text": "x"}, format="json").status_code == 403
        assert support.put(f"{URL}current/", {}, format="json").status_code == 403
        assert support.delete(f"{URL}reading/1/", {}, format="json").status_code == 403
        assert support.post(f"{URL}move-project/", {}, format="json").status_code == 403
        assert support.get(f"{URL}compare/?kind=reading&left=1&right=1").status_code == 403
        project.refresh_from_db()
        assert PromptVersion.objects.count() == 2
        assert not [k for k in kinds_logged() if k.startswith("admin.prompt")]

    def test_nobody_signed_in_is_refused(self):
        assert APIClient().get(URL).status_code == 401


class TestCreatingVersions:
    def test_a_version_gets_the_next_number_and_is_audited(self, boss):
        answer = new_version(boss, text="  Second reading instructions.  ")
        assert answer.status_code == 201
        assert (answer.json()["number"], answer.json()["text"]) == (
            2,
            "Second reading instructions.",
        )
        assert kinds_logged() == ["admin.prompt_created"]

    def test_each_kind_has_its_own_numbers(self, boss):
        new_version(boss, "reading")
        new_version(boss, "reading")
        assert new_version(boss, "scoring").json()["number"] == 2
        assert new_version(boss, "reading").json()["number"] == 4

    def test_a_new_version_changes_nothing_for_existing_or_new_projects_until_made_current(
        self, boss
    ):
        existing = make_project()
        new_version(boss)
        existing.refresh_from_db()
        assert existing.reading_prompt_version == 1
        assert get_setting("ai.reading_prompt_version") == 1
        assert make_project().reading_prompt_version == 1

    def test_an_existing_versions_text_never_changes(self, boss):
        new_version(boss, text="Changed text.")
        assert PromptVersion.objects.get(kind="reading", number=1).text == CV_READING_PROMPT

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "reading", "text": ""},
            {"kind": "reading", "text": "   "},
            {"kind": "other", "text": "x"},
            {"kind": "reading"},
            {"text": "x"},
            {"kind": "reading", "text": "x", "number": 9},
        ],
    )
    def test_bad_input_is_refused(self, boss, body):
        assert boss.post(URL, body, format="json").status_code == 400
        assert PromptVersion.objects.count() == 2

    def test_a_text_over_the_platform_limit_is_refused(self, boss):
        from platform_settings.models import PlatformSetting
        from platform_settings.service import clear_cache

        PlatformSetting.objects.create(key="prompts.max_length", value=100)
        clear_cache()
        assert new_version(boss, text="x" * 101).status_code == 400
        assert new_version(boss, text="x" * 100).status_code == 201


class TestMakingAVersionCurrent:
    def test_new_projects_pin_it_and_existing_ones_keep_theirs(self, boss):
        old = make_project()
        new_version(boss)
        answer = make_current(boss, "reading", 2)
        assert answer.status_code == 200
        old.refresh_from_db()
        assert old.reading_prompt_version == 1
        fresh = make_project(
            reading_prompt_version=get_setting("ai.reading_prompt_version"),
            scoring_prompt_version=get_setting("ai.scoring_prompt_version"),
        )
        assert (fresh.reading_prompt_version, fresh.scoring_prompt_version) == (2, 1)

    def test_creating_a_project_through_the_service_pins_the_current_versions(self, boss):
        from plans import subscriptions as subs
        from plans.models import Plan

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
            monthly_ai_token_cap=1000,
        )
        subs.activate(
            company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30)
        )
        owner = make_company_user(company)
        new_version(boss, "scoring")
        make_current(boss, "scoring", 2)
        project = create_project(
            owner, title="P", job_description="d" * 600, acknowledge_warnings=True
        )
        assert (project.reading_prompt_version, project.scoring_prompt_version) == (1, 2)

    def test_it_is_audited_with_the_reason_and_old_and_new_numbers(self, boss):
        new_version(boss)
        make_current(boss, "reading", 2)
        entry = AuditEvent.objects.get(kind="admin.prompt_made_current")
        assert entry.reason == REASON
        assert entry.details["changes"]["current_version"] == {"old": 1, "new": 2}

    def test_a_reason_is_required(self, boss):
        new_version(boss)
        assert make_current(boss, "reading", 2, reason="").status_code == 400
        assert get_setting("ai.reading_prompt_version") == 1

    def test_the_current_version_again_changes_nothing(self, boss):
        answer = make_current(boss, "reading", 1)
        assert answer.status_code == 400 and answer.json()["error"]["code"] == "nothing_changed"

    def test_an_unknown_version_is_not_found(self, boss):
        assert make_current(boss, "reading", 99).status_code == 404


class TestDeleting:
    def delete(self, boss, kind, number, reason=REASON):
        return boss.delete(f"{URL}{kind}/{number}/", {"reason": reason}, format="json")

    def test_a_version_nobody_uses_is_deleted_and_audited(self, boss):
        new_version(boss)
        assert self.delete(boss, "reading", 2).status_code == 204
        assert not PromptVersion.objects.filter(kind="reading", number=2).exists()
        assert AuditEvent.objects.get(kind="admin.prompt_deleted").reason == REASON

    def test_the_current_version_cannot_be_deleted(self, boss):
        answer = self.delete(boss, "reading", 1)
        assert answer.status_code == 409 and answer.json()["error"]["code"] == "prompt_in_use"
        assert PromptVersion.objects.filter(kind="reading", number=1).exists()

    def test_a_version_pinned_by_a_project_cannot_be_deleted(self, boss):
        new_version(boss)
        make_current(boss, "reading", 2)
        make_project()  # pinned to version 1 by default
        answer = self.delete(boss, "reading", 1)
        assert answer.status_code == 409
        assert answer.json()["error"]["details"]["usage"]["projects"] == 1
        assert PromptVersion.objects.filter(kind="reading", number=1).exists()

    def test_after_the_last_project_moves_away_it_can_be_deleted(self, boss):
        new_version(boss)
        make_current(boss, "reading", 2)
        project = make_project()
        boss.post(
            f"{URL}move-project/",
            {"project_id": str(project.pk), "kind": "reading", "number": 2, "reason": REASON},
            format="json",
        )
        assert self.delete(boss, "reading", 1).status_code == 204

    def test_a_deleted_number_is_never_given_again(self, boss):
        new_version(boss)
        self.delete(boss, "reading", 2)
        assert new_version(boss).json()["number"] == 3

    def test_a_reason_is_required_and_an_unknown_version_is_not_found(self, boss):
        new_version(boss)
        assert self.delete(boss, "reading", 2, reason="").status_code == 400
        assert self.delete(boss, "reading", 99).status_code == 404
        assert self.delete(boss, "other", 1).status_code == 404

    def test_a_version_of_the_other_kind_with_the_same_number_is_not_in_use(self, boss):
        new_version(boss, "scoring")
        make_project()  # pins scoring 1 and reading 1 only
        assert self.delete(boss, "scoring", 2).status_code == 204


class TestMovingAProject:
    def move(self, boss, project, kind="reading", number=2, reason=REASON):
        return boss.post(
            f"{URL}move-project/",
            {"project_id": str(project.pk), "kind": kind, "number": number, "reason": reason},
            format="json",
        )

    def test_the_project_uses_the_other_version_and_others_do_not(self, boss):
        new_version(boss)
        moved, other = make_project(), make_project()
        answer = self.move(boss, moved)
        assert answer.status_code == 200
        assert answer.json() == {"reading_prompt_version": 2, "scoring_prompt_version": 1}
        moved.refresh_from_db()
        other.refresh_from_db()
        assert moved.reading_prompt_version == 2 and other.reading_prompt_version == 1

    def test_moving_can_go_back_to_an_older_version(self, boss):
        new_version(boss)
        project = make_project(reading_prompt_version=2)
        assert self.move(boss, project, number=1).status_code == 200

    def test_the_scoring_pin_is_moved_separately(self, boss):
        new_version(boss, "scoring")
        project = make_project()
        self.move(boss, project, kind="scoring", number=2)
        project.refresh_from_db()
        assert (project.reading_prompt_version, project.scoring_prompt_version) == (1, 2)

    def test_it_is_audited_with_the_company_the_reason_and_the_numbers(self, boss):
        new_version(boss)
        project = make_project()
        self.move(boss, project)
        entry = AuditEvent.objects.get(kind="admin.project_prompt_moved")
        assert entry.company_id == project.company_id and entry.reason == REASON
        assert entry.details["changes"]["reading_version"] == {"old": 1, "new": 2}
        assert entry.details["project_id"] == str(project.pk)

    def test_a_reason_is_required(self, boss):
        new_version(boss)
        project = make_project()
        assert self.move(boss, project, reason="").status_code == 400
        project.refresh_from_db()
        assert project.reading_prompt_version == 1

    def test_the_same_version_changes_nothing(self, boss):
        answer = self.move(boss, make_project(), number=1)
        assert answer.status_code == 400 and answer.json()["error"]["code"] == "nothing_changed"

    def test_an_unknown_version_or_project_is_not_found(self, boss):
        project = make_project()
        assert self.move(boss, project, number=99).status_code == 404
        assert (
            boss.post(
                f"{URL}move-project/",
                {
                    "project_id": "00000000-0000-0000-0000-000000000000",
                    "kind": "reading",
                    "number": 1,
                    "reason": REASON,
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            boss.post(
                f"{URL}move-project/",
                {"project_id": "nope", "kind": "reading", "number": 1, "reason": REASON},
                format="json",
            ).status_code
            == 400
        )


class TestComparing:
    def compare(self, boss, left, right, kind="reading"):
        return boss.get(f"{URL}compare/?kind={kind}&left={left}&right={right}")

    def test_the_texts_are_lined_up_side_by_side_with_the_changes_marked(self, boss):
        new_version(boss, "scoring", "Line one\nLine two\nLine three")
        new_version(boss, "scoring", "Line one\nLine 2\nLine three\nLine four")
        rows = self.compare(boss, 2, 3, "scoring").json()["rows"]
        assert rows == [
            {"left": "Line one", "right": "Line one", "changed": False},
            {"left": "Line two", "right": "Line 2", "changed": True},
            {"left": "Line three", "right": "Line three", "changed": False},
            {"left": "", "right": "Line four", "changed": True},
        ]

    def test_a_line_removed_shows_an_empty_right_side(self, boss):
        new_version(boss, "scoring", "A\nB")
        new_version(boss, "scoring", "A")
        rows = self.compare(boss, 2, 3, "scoring").json()["rows"]
        assert rows[-1] == {"left": "B", "right": "", "changed": True}

    def test_the_same_version_has_no_changed_row(self, boss):
        assert not any(row["changed"] for row in self.compare(boss, 1, 1).json()["rows"])

    def test_the_answer_names_the_two_versions(self, boss):
        new_version(boss)
        answer = self.compare(boss, 1, 2).json()
        assert (answer["kind"], answer["left"], answer["right"]) == ("reading", 1, 2)

    def test_an_unknown_version_is_not_found_and_bad_input_is_refused(self, boss):
        assert self.compare(boss, 1, 99).status_code == 404
        assert boss.get(f"{URL}compare/?kind=reading&left=1").status_code == 400
        assert boss.get(f"{URL}compare/?kind=x&left=1&right=1").status_code == 400
