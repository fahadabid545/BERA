import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

import privatefiles
from cvs import extra_factors
from cvs.models import CvFile, RequirementResult
from cvs.tests.test_processing import Tenant, make_plan
from cvs.tests.test_ranked_list import add
from projects.models import Requirement

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return Tenant(make_plan())


def make_requirement(tenant, text, kind="must", position=1, weight=5):
    return Requirement.objects.create(
        company=tenant.company, project=tenant.project, position=position, kind=kind,
        text=text, weight=weight,
    )  # fmt: skip


def judge(row, item, verdict="met", text=None, model="gpt-x", prompt=3):
    return RequirementResult.objects.create(
        company=row.company, candidate=row.candidate, requirement=item,
        requirement_text=text or item.text, verdict=verdict,
        evidence="" if verdict == "missing" else "quote from the CV", confidence="high",
        model=model, prompt_version=prompt,
    )  # fmt: skip


def detail_url(tenant, row, tail=""):
    return f"/api/company/projects/{tenant.project.pk}/candidates/{row.candidate.pk}/{tail}"


def detail(tenant, row):
    response = tenant.client.get(detail_url(tenant, row))
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def scored(tenant):
    row = add(tenant, "jane.pdf", 82.5, ats=71)
    CvFile.objects.filter(pk=row.pk).update(file_type="pdf")
    row.refresh_from_db()
    return row


class TestSections:
    def test_scores_grade_and_label(self, tenant, scored):
        body = detail(tenant, scored)
        assert body["score"]["score"] == "82.5" and body["score"]["grade"] == "B"
        assert body["score"]["label"] == "strong_match"
        assert body["score"]["outdated"] is False
        assert body["ats"]["score"] == 71

    def test_strengths_risks_questions_and_guide_note(self, tenant, scored):
        from cvs.models import CandidateScore

        CandidateScore.objects.filter(candidate=scored.candidate).update(
            strengths=["Strong Python"], risks=["No cloud"], interview_questions=["Why us?"],
            guide_note="Check cloud.",
        )  # fmt: skip
        body = detail(tenant, scored)["score"]
        assert body["strengths"] == ["Strong Python"] and body["risks"] == ["No cloud"]
        assert body["interview_questions"] == ["Why us?"] and body["guide_note"] == "Check cloud."

    def test_each_requirement_has_its_verdict_and_evidence_quote(self, tenant, scored):
        first = make_requirement(tenant, "Python")
        second = make_requirement(tenant, "Docker", kind="nice", position=2)
        judge(scored, first, "met")
        judge(scored, second, "missing")
        rows = detail(tenant, scored)["requirements"]
        assert [r["text"] for r in rows] == ["Python", "Docker"]
        assert rows[0]["verdict"] == "met" and rows[0]["evidence"] == "quote from the CV"
        assert rows[0]["kind"] == "must" and rows[0]["weight"] == 5
        assert rows[0]["confidence"] == "high" and rows[0]["outdated"] is False
        assert rows[1]["verdict"] == "missing" and rows[1]["evidence"] == ""

    def test_the_stage_and_date_added(self, tenant, scored):
        body = detail(tenant, scored)
        assert body["stage"] == "new" and body["added_at"]
        assert body["file_name"] == "jane.pdf"

    def test_notes_start_empty(self, tenant, scored):
        assert detail(tenant, scored)["notes"] == []

    def test_the_extra_factors(self, tenant, scored):
        extra_factors.store_factors(scored.candidate)
        body = detail(tenant, scored)["factors"]
        assert set(body["values"]) == set(
            ["experience_years", "education", "seniority", "recency",
             "gaps_and_changes", "readability", "confidence"]
        )  # fmt: skip
        assert body["outdated"] is False

    def test_no_factors_stored_yet(self, tenant, scored):
        assert detail(tenant, scored)["factors"] is None

    def test_model_and_prompt_versions(self, tenant, scored):
        item = make_requirement(tenant, "Python")
        judge(scored, item, model="gpt-score", prompt=7)
        models = detail(tenant, scored)["models"]
        assert models["reading"] == {"model": "m", "prompt_version": 1}
        assert models["scoring"] == {"model": "gpt-score", "prompt_version": 7}

    def test_no_scoring_versions_before_any_judgement(self, tenant, scored):
        assert detail(tenant, scored)["models"]["scoring"] is None

    def test_a_candidate_without_a_score_still_shows(self, tenant):
        row = add(tenant, "wait.pdf", status="scoring")
        body = detail(tenant, row)
        assert body["score"] is None and body["ats"] is None
        assert body["status"] == "scoring"


class TestOutdated:
    def test_a_reworded_requirement_is_marked_and_keeps_its_old_result(self, tenant, scored):
        item = make_requirement(tenant, "Python")
        judge(scored, item, "met")
        Requirement.objects.filter(pk=item.pk).update(text="Python and Django")
        row = detail(tenant, scored)["requirements"][0]
        assert row["text"] == "Python and Django"
        assert row["verdict"] == "met" and row["outdated"] is True

    def test_a_new_requirement_is_marked_not_judged(self, tenant, scored):
        make_requirement(tenant, "Kubernetes")
        row = detail(tenant, scored)["requirements"][0]
        assert row["verdict"] is None and row["outdated"] is True

    def test_the_score_is_marked_while_rescoring_is_due(self, tenant, scored):
        from cvs.models import CandidateScore

        CandidateScore.objects.filter(candidate=scored.candidate).update(outdated=True)
        assert detail(tenant, scored)["score"]["outdated"] is True

    def test_factors_for_an_older_job_description_are_marked(self, tenant, scored):
        extra_factors.store_factors(scored.candidate)
        tenant.project.job_description = "A different job"
        tenant.project.save()
        assert detail(tenant, scored)["factors"]["outdated"] is True

    def test_it_shows_the_latest_results_after_rejudging(self, tenant, scored):
        item = make_requirement(tenant, "Python")
        old = judge(scored, item, "missing")
        old.delete()
        judge(scored, item, "met")
        assert detail(tenant, scored)["requirements"][0]["verdict"] == "met"


class TestFailedAndDeleted:
    def test_a_failed_candidate_carries_the_reason(self, tenant, scored):
        CvFile.objects.filter(pk=scored.pk).update(
            status="failed", failure_reason="AI scoring failed. Try again."
        )
        body = detail(tenant, scored)
        assert body["status"] == "failed"
        assert body["failure_reason"] == "AI scoring failed. Try again."
        assert body["score"]["score"] == "82.5"  # the old score stays

    def test_a_deleted_candidate_is_not_found(self, tenant, scored):
        from cvs.candidates import remove_candidate

        link = detail_url(tenant, scored)
        remove_candidate(scored.candidate)
        response = tenant.client.get(link)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestContactAndSecurity:
    def test_the_contact_details_are_here(self, tenant, scored):
        contact = detail(tenant, scored)["contact"]
        assert contact["name"] == "Jane Example" and contact["email"] == "jane@example.com"
        assert set(contact) == {"name", "email", "phone", "address"}

    def test_contact_details_are_in_no_other_candidate_answer(self, tenant, scored):
        for path in ("", "recommendation/"):
            text = tenant.client.get(
                f"/api/company/projects/{tenant.project.pk}/candidates/{path}"
                if path == ""
                else detail_url(tenant, scored, path)
            ).content.decode()
            assert "jane@example.com" not in text and "Jane Example" not in text

    def test_another_company_gets_not_found(self, tenant, scored):
        other = Tenant(make_plan())
        link = detail_url(tenant, scored)
        assert other.client.get(link).status_code == 404
        assert other.client.get(link + "cv/").status_code == 404

    def test_a_candidate_of_another_project_is_not_found(self, tenant, scored):
        from projects.models import Project

        second = Project.objects.create(
            company=tenant.company, title="Other", job_description="x", reading_model="m",
            created_by=tenant.owner,
        )  # fmt: skip
        link = f"/api/company/projects/{second.pk}/candidates/{scored.candidate.pk}/"
        assert tenant.client.get(link).status_code == 404

    def test_signed_out_is_refused(self, tenant, scored):
        assert APIClient().get(detail_url(tenant, scored)).status_code == 401
        assert APIClient().get(detail_url(tenant, scored, "cv/")).status_code == 401

    def test_staff_accounts_are_refused(self, tenant, scored):
        from ai.tests.test_model_settings import admin_client

        boss, _ = admin_client("super")
        assert boss.get(detail_url(tenant, scored)).status_code in (401, 403)
        assert boss.get(detail_url(tenant, scored, "cv/")).status_code in (401, 403)

    def test_the_query_count_is_small_and_fixed(self, tenant, scored):
        for number in range(8):
            judge(scored, make_requirement(tenant, f"R{number}", position=number), "met")
        with CaptureQueriesContext(connection) as many:
            detail(tenant, scored)
        assert len(many) < 25


class TestOriginalCv:
    @pytest.fixture
    def stored(self, tenant, scored):
        privatefiles.save_file(scored.storage_key, b"%PDF-1.4 fake")
        return scored

    def test_the_cv_says_whether_it_can_be_previewed(self, tenant, scored):
        assert detail(tenant, scored)["cv"] == {"file_type": "pdf", "can_preview": True}
        CvFile.objects.filter(pk=scored.pk).update(file_type="docx")
        assert detail(tenant, scored)["cv"]["can_preview"] is False

    def test_a_pdf_is_shown_inline(self, tenant, stored):
        response = tenant.client.get(detail_url(tenant, stored, "cv/"))
        assert response.status_code == 200 and response.content == b"%PDF-1.4 fake"
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline")
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]

    def test_download_saves_it_with_its_name(self, tenant, stored):
        response = tenant.client.get(detail_url(tenant, stored, "cv/?download=1"))
        assert response["Content-Disposition"].startswith("attachment")
        assert "jane.pdf" in response["Content-Disposition"]

    def test_a_docx_is_never_shown_inline(self, tenant, stored):
        CvFile.objects.filter(pk=stored.pk).update(file_type="docx")
        response = tenant.client.get(detail_url(tenant, stored, "cv/"))
        assert response["Content-Disposition"].startswith("attachment")
        assert "wordprocessingml" in response["Content-Type"]

    def test_a_missing_file_gives_a_clear_message(self, tenant, scored):
        response = tenant.client.get(detail_url(tenant, scored, "cv/"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "cv_file_missing"

    def test_an_unavailable_store_gives_a_clear_message(self, tenant, stored, monkeypatch):
        def broken(key):
            raise privatefiles.StorageUnavailable()

        monkeypatch.setattr(privatefiles, "read_file", broken)
        response = tenant.client.get(detail_url(tenant, stored, "cv/"))
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage_unavailable"
