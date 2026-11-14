import json
from datetime import timedelta

import pytest
from django.utils import timezone

from ai import client
from ai.client import AiAnswer
from core.tests.factories import make_company, make_company_user
from cvs import candidates, processing, service
from cvs.models import Candidate, CvContact, CvFile, CvProfile
from cvs.tests.test_ai_reading import CV_TEXT, GOOD_ANSWER
from plans import subscriptions as subs
from plans.models import Plan
from projects import deletion
from projects.models import Project
from usage import service as usage

pytestmark = pytest.mark.django_db


def make_cv(company=None, project=None):
    if company is None:
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
        subs.activate(company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
    owner = project.created_by if project else make_company_user(company)  # one owner per company
    project = project or Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model="m",
        created_by=owner,
    )
    cv = CvFile.objects.create(
        company=company,
        project=project,
        original_name="cv.pdf",
        file_type="pdf",
        size_bytes=1,
        storage_key=f"cvs/{company.pk}/{CvFile.objects.count()}",
        uploaded_by=owner,
        status="reading",
    )
    usage.accept_cv(company.pk, cv.pk, project.pk)
    return cv


def add_profile(cv):
    CvProfile.objects.create(
        company_id=cv.company_id, cv_file=cv, content={"skills": []}, model="m", prompt_version=1
    )
    CvContact.objects.create(company_id=cv.company_id, cv_file=cv, name="Jane Example")
    return CvFile.objects.get(pk=cv.pk)


@pytest.fixture
def cv():
    return add_profile(make_cv())


@pytest.fixture(autouse=True)
def stored_files_are_removed_quietly(monkeypatch):
    removed = []
    monkeypatch.setattr(service.storage, "delete_file", removed.append)
    return removed


class TestCreated:
    def test_a_candidate_links_project_file_profile_and_contact(self, cv):
        candidate = candidates.create_candidate(cv)
        assert candidate.project_id == cv.project_id and candidate.cv_file_id == cv.pk
        assert candidate.profile == cv.profile and candidate.contact == cv.contact
        assert candidate.company_id == cv.company_id

    def test_the_stage_starts_as_new(self, cv):
        assert candidates.create_candidate(cv).stage == "new"
        assert [choice for choice, _ in Candidate.Stage.choices] == ["new"]

    def test_creating_again_gives_the_same_candidate(self, cv):
        first = candidates.create_candidate(cv)
        assert candidates.create_candidate(cv).pk == first.pk
        assert Candidate.objects.count() == 1

    def test_a_cv_without_a_profile_cannot_become_a_candidate(self):
        with pytest.raises(CvProfile.DoesNotExist):
            candidates.create_candidate(make_cv())
        assert not Candidate.objects.exists()


class TestSlot:
    def test_the_slot_sits_between_the_fairness_guard_and_scoring(self):
        slots = processing.SLOTS
        assert slots.index("fairness_guard") < slots.index("candidate_record")
        assert slots.index("candidate_record") < slots.index("scoring")

    def test_the_step_is_plugged_into_its_slot(self):
        assert processing.STEPS["candidate_record"] is candidates.make_the_candidate


class TestPipeline:
    """The real steps, from the text to the candidate, with a stubbed AI."""

    @pytest.fixture
    def pipeline(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            client,
            "_send",
            lambda **call: sent.append(call) or AiAnswer(json.dumps(GOOD_ANSWER), 10, 5),
        )
        real = dict(processing.STEPS)
        processing.STEPS["text_reading"] = lambda context: context.state.update(text=CV_TEXT)
        processing.STEPS.pop("requirement_evaluation")  # judged in test_requirement_evaluation.py
        processing.STEPS.pop("ats_score")  # in test_ats_score.py
        processing.STEPS.pop("extra_factors")  # in test_extra_factors.py
        processing.STEPS.pop("scoring")  # in test_score_calculation.py
        yield sent
        processing.STEPS.clear()
        processing.STEPS.update(real)

    def run(self, row):
        row.claim_token = "11111111-1111-1111-1111-111111111111"
        row.save()
        processing.run_item(CvFile.objects.get(pk=row.pk))
        return CvFile.objects.get(pk=row.pk)

    def test_a_cv_that_is_read_becomes_a_candidate_before_scoring(self, pipeline):
        row = make_cv()
        seen = []
        processing.STEPS["scoring"] = lambda context: seen.append(
            Candidate.objects.filter(cv_file=context.cv_file).exists()
        )
        finished = self.run(row)
        assert finished.status == "done" and seen == [True]
        assert Candidate.objects.filter(cv_file=row, stage="new").count() == 1

    def test_a_cv_that_fails_reading_has_no_candidate_and_shows_as_failed_with_a_reason(
        self, pipeline, monkeypatch
    ):
        monkeypatch.setattr(client, "_send", lambda **call: AiAnswer("not json", 1, 1))
        finished = self.run(make_cv())
        assert finished.status == "failed" and finished.failure_reason
        assert not Candidate.objects.exists()

    def test_a_retry_after_a_failed_score_keeps_the_same_candidate_and_reads_the_cv_once(
        self, pipeline
    ):
        row = make_cv()
        outcomes = iter([RuntimeError("scoring broke"), None])

        def scoring(context):
            outcome = next(outcomes)
            if outcome:
                raise outcome

        processing.STEPS["scoring"] = scoring
        self.run(row)  # scoring fails: the candidate stays, the CV waits for another try
        first = Candidate.objects.get(cv_file=row)
        CvFile.objects.filter(pk=row.pk).update(next_attempt_at=processing._now())
        finished = self.run(CvFile.objects.get(pk=row.pk))
        assert finished.status == "done"
        assert Candidate.objects.get(cv_file=row).pk == first.pk
        assert len(pipeline) == 1  # one AI reading in all


class TestRemoval:
    def test_removing_a_candidate_removes_file_profile_contact_and_record(
        self, cv, stored_files_are_removed_quietly
    ):
        candidate = candidates.create_candidate(cv)
        candidates.remove_candidate(candidate)
        assert not any(
            model.objects.exists() for model in (Candidate, CvProfile, CvContact, CvFile)
        )
        assert stored_files_are_removed_quietly == [cv.storage_key]

    def test_removing_a_candidate_leaves_the_usage_history(self, cv):
        candidates.create_candidate(cv)
        before = usage.current_usage(cv.company_id)
        candidates.remove_candidate(Candidate.objects.get(cv_file=cv))
        assert usage.current_usage(cv.company_id) == before

    def test_removing_one_candidate_leaves_the_others(self, cv):
        other = add_profile(make_cv(cv.company, cv.project))
        candidates.create_candidate(cv)
        candidates.create_candidate(other)
        candidates.remove_candidate(Candidate.objects.get(cv_file=cv))
        assert Candidate.objects.get().cv_file_id == other.pk

    def test_deleting_a_project_removes_all_its_candidates_and_their_data(self, cv):
        other = add_profile(make_cv(cv.company, cv.project))
        failed = make_cv(cv.company, cv.project)
        candidates.create_candidate(cv)
        candidates.create_candidate(other)
        owner = cv.uploaded_by
        deletion.delete_project(owner, cv.project)
        assert not any(
            model.objects.exists() for model in (Candidate, CvProfile, CvContact, CvFile)
        )
        assert failed.pk and not Project.objects.exists()

    def test_deleting_a_project_leaves_other_projects_candidates(self, cv):
        other_project = Project.objects.create(
            company=cv.company,
            title="Other",
            job_description="t",
            reading_model="m",
            created_by=cv.uploaded_by,
        )
        kept = add_profile(make_cv(cv.company, other_project))
        candidates.create_candidate(cv)
        candidates.create_candidate(kept)
        deletion.delete_project(cv.uploaded_by, cv.project)
        assert Candidate.objects.get().project_id == other_project.pk

    def test_a_discarded_flagged_duplicate_removes_its_candidate(self, cv):
        candidates.create_candidate(cv)
        CvFile.objects.filter(pk=cv.pk).update(review="flagged")
        from cvs.duplicates import discard_flagged_cv

        discard_flagged_cv(CvFile.objects.get(pk=cv.pk))
        assert not Candidate.objects.exists() and not CvProfile.objects.exists()


class TestAnotherCompany:
    def test_a_candidate_belongs_to_its_own_company_and_is_removed_with_its_own_project_only(
        self,
    ):
        mine, theirs = add_profile(make_cv()), add_profile(make_cv())
        candidates.create_candidate(mine)
        candidates.create_candidate(theirs)
        assert Candidate.objects.get(cv_file=mine).company_id == mine.company_id
        assert Candidate.objects.filter(company_id=mine.company_id).count() == 1
        deletion.delete_project(mine.uploaded_by, mine.project)
        assert Candidate.objects.get().company_id == theirs.company_id
