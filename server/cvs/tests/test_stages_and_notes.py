import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from companies.models import CompanyUser
from core.tests.factories import make_company_user, start_session_for
from cvs.candidates import remove_candidate
from cvs.models import Candidate, CandidateNote, StageChange
from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add, names

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def stage_url(tenant):
    return f"/api/company/projects/{tenant.project.pk}/candidates/stage/"


def move(tenant, rows, stage, client=None):
    ids = [str(r.candidate.pk) for r in rows]
    return (client or tenant.client).post(
        stage_url(tenant), {"candidate_ids": ids, "stage": stage}, format="json"
    )


def stage_of(row):
    return Candidate.objects.get(pk=row.candidate.pk).stage


def detail(tenant, row, client=None):
    link = f"/api/company/projects/{tenant.project.pk}/candidates/{row.candidate.pk}/"
    return (client or tenant.client).get(link).json()


def colleague(tenant):
    person = make_company_user(tenant.company, role="member")
    issued = start_session_for(
        user_id=person.pk, role="member", company_id=tenant.company.pk, kind="company"
    )
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def trio(tenant):
    return [add(tenant, f"{n}.pdf", score, minutes=i) for i, (n, score) in enumerate(
        [("a", 90), ("b", 70), ("c", 50)]
    )]  # fmt: skip


class TestStages:
    def test_the_five_stages(self):
        assert Candidate.Stage.values == [
            "new", "shortlisted", "interview", "approved", "rejected",
        ]  # fmt: skip

    def test_one_candidate_moves(self, tenant, trio):
        response = move(tenant, trio[:1], "shortlisted")
        assert response.status_code == 200
        assert response.json() == {"changed": 1, "unchanged": 0}
        assert stage_of(trio[0]) == "shortlisted" and stage_of(trio[1]) == "new"

    def test_many_move_at_once(self, tenant, trio):
        assert move(tenant, trio, "interview").json()["changed"] == 3
        assert {stage_of(r) for r in trio} == {"interview"}

    def test_one_entry_of_history_for_each_change(self, tenant, trio):
        move(tenant, trio, "shortlisted")
        assert StageChange.objects.count() == 3
        entry = StageChange.objects.first()
        assert (entry.from_stage, entry.to_stage) == ("new", "shortlisted")
        assert entry.changed_by_id == tenant.owner.pk and entry.created_at

    def test_a_candidate_already_there_gets_no_entry(self, tenant, trio):
        move(tenant, trio[:1], "approved")
        response = move(tenant, trio, "approved")
        assert response.json() == {"changed": 2, "unchanged": 1}
        assert StageChange.objects.filter(candidate=trio[0].candidate).count() == 1

    def test_the_same_candidate_twice_counts_once(self, tenant, trio):
        ids = [str(trio[0].candidate.pk)] * 2
        response = tenant.client.post(
            stage_url(tenant), {"candidate_ids": ids, "stage": "interview"}, format="json"
        )
        assert response.json()["changed"] == 1

    def test_history_is_shown_newest_first_with_who_and_when(self, tenant, trio):
        move(tenant, trio[:1], "shortlisted")
        move(tenant, trio[:1], "interview")
        history = detail(tenant, trio[0])["history"]
        assert [(h["from_stage"], h["to_stage"]) for h in history] == [
            ("shortlisted", "interview"), ("new", "shortlisted"),
        ]  # fmt: skip
        assert history[0]["by"] == tenant.owner.name and history[0]["at"]
        assert detail(tenant, trio[0])["stage"] == "interview"

    def test_history_names_each_person(self, tenant, trio):
        person, client = colleague(tenant)
        move(tenant, trio[:1], "shortlisted", client)
        assert detail(tenant, trio[0])["history"][0]["by"] == person.name

    @pytest.mark.parametrize("stage", ["hired", "", None, "NEW"])
    def test_an_unknown_stage_is_refused(self, tenant, trio, stage):
        response = move(tenant, trio, stage)
        assert response.status_code == 400 and "stage" in response.json()["error"]["fields"]
        assert stage_of(trio[0]) == "new"

    @pytest.mark.parametrize("ids", [[], None, "x"])
    def test_nothing_chosen_is_refused(self, tenant, ids):
        response = tenant.client.post(
            stage_url(tenant), {"candidate_ids": ids, "stage": "new"}, format="json"
        )
        assert response.status_code == 400
        assert "candidate_ids" in response.json()["error"]["fields"]

    def test_too_many_at_once_is_refused(self, tenant, trio):
        set_setting("candidates.bulk_max", 2)
        assert move(tenant, trio, "interview").status_code == 400
        assert stage_of(trio[0]) == "new"

    def test_another_companys_candidate_makes_it_all_not_found_and_changes_nothing(
        self, tenant, trio
    ):
        other = Tenant(make_plan())
        foreign = add(other, "theirs.pdf", 80)
        response = move(tenant, [*trio, foreign], "rejected")
        assert response.status_code == 404
        assert {stage_of(r) for r in [*trio, foreign]} == {"new"}
        assert StageChange.objects.count() == 0

    def test_a_candidate_of_another_project_is_not_found(self, tenant, trio):
        from projects.models import Project

        second = Project.objects.create(
            company=tenant.company, title="Other", job_description="x", reading_model="m",
            created_by=tenant.owner,
        )  # fmt: skip
        link = f"/api/company/projects/{second.pk}/candidates/stage/"
        response = tenant.client.post(
            link,
            {"candidate_ids": [str(trio[0].candidate.pk)], "stage": "interview"},
            format="json",
        )
        assert response.status_code == 404

    def test_a_malformed_id_is_not_found(self, tenant):
        response = tenant.client.post(
            stage_url(tenant), {"candidate_ids": ["nope"], "stage": "new"}, format="json"
        )
        assert response.status_code == 404

    def test_signed_out_and_staff_are_refused(self, tenant, trio):
        from ai.tests.test_model_settings import admin_client

        body = {"candidate_ids": [str(trio[0].candidate.pk)], "stage": "interview"}
        assert APIClient().post(stage_url(tenant), body, format="json").status_code == 401
        boss, _ = admin_client("super")
        assert boss.post(stage_url(tenant), body, format="json").status_code in (401, 403)

    def test_history_goes_with_the_candidate(self, tenant, trio):
        move(tenant, trio[:1], "shortlisted")
        remove_candidate(trio[0].candidate)
        assert StageChange.objects.count() == 0

    def test_the_query_count_does_not_grow_with_the_candidates(self, tenant, trio):
        with CaptureQueriesContext(connection) as few:
            move(tenant, trio[:1], "interview")
        more = [add(tenant, f"x{n}.pdf", 40, minutes=20 + n) for n in range(15)]
        with CaptureQueriesContext(connection) as many:
            move(tenant, more, "interview")
        assert len(many) == len(few)


class TestRejectedAreHidden:
    def test_hidden_from_the_default_list(self, tenant, trio):
        move(tenant, trio[1:2], "rejected")
        assert names(tenant) == ["a.pdf", "c.pdf"]

    def test_the_stage_filter_brings_them_back(self, tenant, trio):
        move(tenant, trio[1:2], "rejected")
        assert names(tenant, "?stage=rejected") == ["b.pdf"]
        assert names(tenant, "?stage=new,rejected") == ["a.pdf", "b.pdf", "c.pdf"]

    def test_other_stage_filters_do_not_show_them(self, tenant, trio):
        move(tenant, trio[1:2], "rejected")
        assert names(tenant, "?stage=new") == ["a.pdf", "c.pdf"]

    def test_the_count_leaves_them_out(self, tenant, trio):
        move(tenant, trio[1:2], "rejected")
        body = tenant.client.get(f"/api/company/projects/{tenant.project.pk}/candidates/").json()
        assert body["count"] == 2

    def test_cvs_still_processing_stay_listed(self, tenant, trio):
        add(tenant, "wait.pdf", status="waiting", minutes=9)
        assert "wait.pdf" in names(tenant)

    def test_other_stages_stay_in_the_default_list(self, tenant, trio):
        move(tenant, trio, "approved")
        assert len(names(tenant)) == 3


def notes_url(tenant, row, tail=""):
    return f"/api/company/projects/{tenant.project.pk}/candidates/{row.candidate.pk}/notes/{tail}"


class TestNotes:
    def test_add_and_show(self, tenant, trio):
        response = tenant.client.post(notes_url(tenant, trio[0]), {"text": " Call Monday "})
        assert response.status_code == 201
        assert response.json()["text"] == "Call Monday" and response.json()["mine"] is True
        shown = detail(tenant, trio[0])["notes"]
        assert [n["text"] for n in shown] == ["Call Monday"]
        assert shown[0]["author"] == tenant.owner.name and shown[0]["created_at"]

    def test_newest_first(self, tenant, trio):
        for text in ("one", "two"):
            tenant.client.post(notes_url(tenant, trio[0]), {"text": text})
        assert [n["text"] for n in detail(tenant, trio[0])["notes"]] == ["two", "one"]

    def test_the_longest_note_is_accepted_and_one_more_is_refused(self, tenant, trio):
        ok = tenant.client.post(notes_url(tenant, trio[0]), {"text": "x" * 2000})
        assert ok.status_code == 201
        bad = tenant.client.post(notes_url(tenant, trio[0]), {"text": "x" * 2001})
        assert bad.status_code == 400 and "text" in bad.json()["error"]["fields"]

    @pytest.mark.parametrize("text", ["", "   ", None, 5])
    def test_an_empty_note_is_refused(self, tenant, trio, text):
        response = tenant.client.post(notes_url(tenant, trio[0]), {"text": text}, format="json")
        assert response.status_code == 400

    def test_the_author_can_change_and_remove_it(self, tenant, trio):
        note = tenant.client.post(notes_url(tenant, trio[0]), {"text": "old"}).json()
        changed = tenant.client.patch(notes_url(tenant, trio[0], f"{note['id']}/"), {"text": "new"})
        assert changed.status_code == 200 and changed.json()["text"] == "new"
        gone = tenant.client.delete(notes_url(tenant, trio[0], f"{note['id']}/"))
        assert gone.status_code == 204 and CandidateNote.objects.count() == 0

    def test_a_colleague_sees_it_but_cannot_change_or_remove_it(self, tenant, trio):
        note = tenant.client.post(notes_url(tenant, trio[0]), {"text": "mine"}).json()
        person, client = colleague(tenant)
        seen = detail(tenant, trio[0], client)["notes"][0]
        assert seen["text"] == "mine" and seen["mine"] is False
        link = notes_url(tenant, trio[0], f"{note['id']}/")
        refused = client.patch(link, {"text": "hijack"})
        assert refused.status_code == 403 and refused.json()["error"]["code"] == "not_note_author"
        assert client.delete(link).status_code == 403
        assert CandidateNote.objects.get().text == "mine"

    def test_another_companys_candidate_is_not_found(self, tenant, trio):
        other = Tenant(make_plan())
        assert other.client.post(notes_url(tenant, trio[0]), {"text": "x"}).status_code == 404

    def test_a_note_of_another_candidate_is_not_found(self, tenant, trio):
        note = tenant.client.post(notes_url(tenant, trio[0]), {"text": "x"}).json()
        link = notes_url(tenant, trio[1], f"{note['id']}/")
        assert tenant.client.patch(link, {"text": "y"}).status_code == 404
        assert tenant.client.delete(notes_url(tenant, trio[1], "nope/")).status_code == 404

    def test_notes_go_with_the_candidate(self, tenant, trio):
        tenant.client.post(notes_url(tenant, trio[0]), {"text": "x"})
        remove_candidate(trio[0].candidate)
        assert CandidateNote.objects.count() == 0

    def test_signed_out_and_staff_are_refused(self, tenant, trio):
        from ai.tests.test_model_settings import admin_client

        assert APIClient().post(notes_url(tenant, trio[0]), {"text": "x"}).status_code == 401
        boss, _ = admin_client("super")
        assert boss.post(notes_url(tenant, trio[0]), {"text": "x"}).status_code in (401, 403)

    def test_the_text_is_never_logged(self, tenant, trio, caplog):
        tenant.client.post(notes_url(tenant, trio[0]), {"text": "secret-note-words"})
        assert "secret-note-words" not in caplog.text


def test_removing_a_person_is_not_needed_for_history(tenant):
    assert CompanyUser._meta.get_field("name")
