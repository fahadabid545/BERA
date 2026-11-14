import json
import logging
from datetime import date, timedelta

import pytest
from django.utils import timezone

from ai import client
from ai.client import AiAnswer, AiUnavailable
from core.tests.factories import make_company, make_company_user
from cvs import processing, profile_reading
from cvs.models import CvContact, CvFile, CvProfile
from cvs.processing import PermanentFailure
from cvs.profile_checks import UnusableAnswer, check_answer, years_of_experience
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from usage import service as usage

pytestmark = pytest.mark.django_db

CV_TEXT = (
    "Jane Example\njane@example.com +1 (555) 010-2030\n12 Sample Street, Exampleville\n"
    "Senior Backend Engineer, 2018 - present. Built services in Python and Django, "
    "and used PostgreSQL daily.\nBackend Developer, 2014 - 2017, wrote C++ and Go.\n"
    "BSc Computer Science, University of Examples.\nCertified Kubernetes Administrator.\n"
    "Languages: English, German."
)
GOOD_ANSWER = {
    "contact": {
        "name": "Jane Example",
        "email": "jane@example.com",
        "phone": "+1 (555) 010-2030",
        "address": "12 Sample Street, Exampleville",
    },
    "skills": ["Python", "Django", "PostgreSQL", "C++", "Go"],
    "jobs": [
        {"title": "Senior Backend Engineer", "start": "2018", "end": "present"},
        {"title": "Backend Developer", "start": "2014", "end": "2017"},
    ],
    "years_of_experience": 99,
    "education": [{"degree": "BSc Computer Science", "institution": "University of Examples"}],
    "certifications": ["Certified Kubernetes Administrator"],
    "languages": ["English", "German"],
    "summary": "A backend engineer who builds services in Python.",
}


def answer_with(**changes):
    return json.dumps({**GOOD_ANSWER, **changes})


class StubAi:
    """Replaces the one place that talks to the provider; answers in order."""

    def __init__(self, monkeypatch):
        self.answers, self.calls = [], []
        monkeypatch.setattr(client, "_send", self._send)

    def _send(self, **call):
        self.calls.append(call)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return AiAnswer(text=answer, tokens_in=100, tokens_out=50)


@pytest.fixture
def ai(monkeypatch):
    return StubAi(monkeypatch)


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def make_cv(cap=10000):
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
        monthly_ai_token_cap=cap,
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timedelta(days=30))
    owner = make_company_user(company)
    project = Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model="pinned-model",
        prompt_version="pinned-prompt",
        created_by=owner,
    )
    cv = CvFile.objects.create(
        company=company,
        project=project,
        original_name="cv.pdf",
        file_type="pdf",
        size_bytes=1,
        storage_key=f"cvs/{company.pk}/x",
        uploaded_by=owner,
        status="reading",
    )
    usage.accept_cv(company.pk, cv.pk, project.pk)
    return cv


@pytest.fixture
def cv():
    return make_cv()


class TestProfileIsCreated:
    def test_the_profile_holds_the_checked_fields_and_the_model_and_prompt_version(self, cv, ai):
        ai.answers = [answer_with()]
        saved = profile_reading.read_profile(cv, CV_TEXT)
        assert saved.model == "pinned-model" and saved.prompt_version == "pinned-prompt"
        content = saved.content
        assert content["skills"] == ["Python", "Django", "PostgreSQL", "C++", "Go"]
        assert [job["title"] for job in content["jobs"]] == [
            "Senior Backend Engineer",
            "Backend Developer",
        ]
        assert content["jobs"][0] == {
            "title": "Senior Backend Engineer",
            "start": "2018",
            "end": "present",
        }
        assert content["education"] == [
            {"degree": "BSc Computer Science", "institution": "University of Examples"}
        ]
        assert content["certifications"] == ["Certified Kubernetes Administrator"]
        assert content["languages"] == ["English", "German"]
        assert content["summary"].startswith("A backend engineer")

    def test_the_call_uses_the_pinned_model_and_the_cv_text(self, cv, ai):
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        assert ai.calls[0]["model"] == "pinned-model" and ai.calls[0]["text"] == CV_TEXT

    def test_tokens_go_to_the_cvs_company_and_period(self, cv, ai):
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        current = usage.current_usage(cv.company_id)
        assert (current["tokens_in"], current["tokens_out"]) == (100, 50)

    def test_the_output_limit_comes_from_the_platform_settings(self, cv, ai):
        set_setting("ai.cv_reading_max_output_tokens", 777)
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        assert ai.calls[0]["max_output_tokens"] == 777


class TestReadOnceAndReuse:
    def test_a_cv_with_a_profile_is_never_read_again(self, cv, ai):
        ai.answers = [answer_with()]
        first = profile_reading.read_profile(cv, CV_TEXT)
        again = profile_reading.read_profile(cv, CV_TEXT)
        assert again.pk == first.pk and len(ai.calls) == 1
        assert CvProfile.objects.filter(cv_file=cv).count() == 1

    def test_a_retry_after_a_later_failure_costs_no_tokens(self, cv, ai):
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        before = usage.current_usage(cv.company_id)["tokens_in"]
        profile_reading.read_profile(cv, CV_TEXT)
        assert usage.current_usage(cv.company_id)["tokens_in"] == before

    def test_a_profile_is_kept_when_the_ai_is_down_later(self, cv, ai):
        ai.answers = [answer_with(), AiUnavailable("down")]
        saved = profile_reading.read_profile(cv, CV_TEXT)
        assert profile_reading.read_profile(cv, CV_TEXT).pk == saved.pk


class TestInvalidAnswers:
    @pytest.mark.parametrize(
        "bad",
        [
            "not json at all",
            "[]",
            json.dumps({**GOOD_ANSWER, "skills": "Python"}),
            json.dumps({k: v for k, v in GOOD_ANSWER.items() if k != "jobs"}),
            json.dumps({**GOOD_ANSWER, "summary": 5}),
            json.dumps({**GOOD_ANSWER, "skills": [], "jobs": []}),
        ],
    )
    def test_an_invalid_or_incomplete_answer_is_asked_for_once_more(self, cv, ai, bad):
        ai.answers = [bad, answer_with()]
        saved = profile_reading.read_profile(cv, CV_TEXT)
        assert len(ai.calls) == 2 and saved.content["skills"]

    def test_two_bad_answers_fail_the_cv_with_a_reason_and_save_nothing(self, cv, ai):
        ai.answers = ["nope", "still nope"]
        with pytest.raises(PermanentFailure) as failure:
            profile_reading.read_profile(cv, CV_TEXT)
        assert str(failure.value) == profile_reading.UNUSABLE_REASON
        assert len(ai.calls) == 2
        assert not CvProfile.objects.exists() and not CvContact.objects.exists()

    def test_both_calls_are_counted(self, cv, ai):
        ai.answers = ["nope", "still nope"]
        with pytest.raises(PermanentFailure):
            profile_reading.read_profile(cv, CV_TEXT)
        assert usage.current_usage(cv.company_id)["tokens_in"] == 200

    def test_the_number_of_retries_is_a_platform_setting(self, cv, ai):
        set_setting("ai.invalid_answer_retries", 0)
        ai.answers = ["nope"]
        with pytest.raises(PermanentFailure):
            profile_reading.read_profile(cv, CV_TEXT)
        assert len(ai.calls) == 1

    def test_an_unavailable_ai_is_left_to_the_processing_retries(self, cv, ai):
        ai.answers = [AiUnavailable("down")]
        with pytest.raises(AiUnavailable):
            profile_reading.read_profile(cv, CV_TEXT)
        assert not CvProfile.objects.exists()

    def test_a_company_over_its_token_cap_is_not_read_and_the_reason_is_clear(self, ai):
        capped = make_cv(cap=10)
        usage.add_tokens(capped.company_id, 10, 0, 0)
        with pytest.raises(PermanentFailure) as failure:
            profile_reading.read_profile(capped, CV_TEXT)
        assert str(failure.value) == profile_reading.AI_PAUSED_REASON and not ai.calls


class TestInventedFactsAreRemoved:
    def check(self, **changes):
        return check_answer(answer_with(**changes), CV_TEXT)

    def test_a_skill_not_in_the_cv_is_removed(self):
        profile, _ = self.check(skills=["Python", "Rust", "Kafka"])
        assert profile["skills"] == ["Python"]

    def test_a_short_skill_must_match_whole_words(self):
        profile, _ = self.check(skills=["G", "Pyth"])
        assert profile["skills"] == []

    def test_matching_ignores_case_and_spacing(self):
        profile, _ = self.check(skills=["python", "post gres"], certifications=[])
        assert profile["skills"] == ["python"]

    def test_a_job_title_not_in_the_cv_is_removed(self):
        profile, _ = self.check(
            jobs=[
                {"title": "Chief Technology Officer", "start": "2018", "end": "present"},
                {"title": "Backend Developer", "start": "2014", "end": "2017"},
            ]
        )
        assert [job["title"] for job in profile["jobs"]] == ["Backend Developer"]

    def test_a_date_whose_year_is_not_in_the_cv_is_removed_but_the_job_stays(self):
        profile, _ = self.check(
            jobs=[{"title": "Backend Developer", "start": "2001", "end": "2017"}]
        )
        assert profile["jobs"] == [{"title": "Backend Developer", "start": None, "end": "2017"}]

    @pytest.mark.parametrize("bad", ["last year", "2014-13", "14", "2014-1", ""])
    def test_a_badly_formed_date_is_removed(self, bad):
        profile, _ = self.check(jobs=[{"title": "Backend Developer", "start": bad, "end": "2017"}])
        assert profile["jobs"][0]["start"] is None

    def test_education_not_in_the_cv_is_removed(self):
        profile, _ = self.check(
            education=[
                {"degree": "PhD Physics", "institution": "University of Examples"},
                {"degree": "MBA", "institution": "Elsewhere College"},
            ]
        )
        assert profile["education"] == [{"degree": "", "institution": "University of Examples"}]

    def test_certifications_and_languages_are_checked(self):
        profile, _ = self.check(
            certifications=["Certified Kubernetes Administrator", "AWS Architect"],
            languages=["English", "French"],
        )
        assert profile["certifications"] == ["Certified Kubernetes Administrator"]
        assert profile["languages"] == ["English"]

    def test_repeated_items_are_kept_once(self):
        profile, _ = self.check(skills=["Python", "python", "PYTHON"])
        assert profile["skills"] == ["Python"]

    def test_the_number_and_length_of_items_are_limited_by_platform_settings(self):
        set_setting("profile.max_items", 2)
        set_setting("profile.item_max_length", 20)
        profile, _ = self.check(skills=["Python", "Django", "PostgreSQL", "Go"])
        assert profile["skills"] == ["Python", "Django"]
        long_skill = "Senior Backend Engineer, 2018 - present"
        assert self.check(skills=[long_skill, "Go"])[0]["skills"] == ["Go"]

    def test_a_years_figure_the_ai_made_up_is_ignored(self):
        profile, _ = self.check()
        assert profile["years_of_experience"] != 99

    def test_fields_the_ai_adds_never_reach_the_profile(self):
        profile, _ = self.check(age=41, gender="female", photo="a smiling face")
        assert set(profile) == {
            "skills",
            "certifications",
            "languages",
            "jobs",
            "education",
            "years_of_experience",
            "summary",
        }

    def test_a_summary_that_is_too_long_is_dropped(self):
        set_setting("profile.summary_max_length", 50)
        profile, _ = self.check(summary="x" * 51)
        assert profile["summary"] == ""

    def test_answers_with_nothing_surviving_are_unusable(self):
        with pytest.raises(UnusableAnswer):
            self.check(skills=["Rust"], jobs=[{"title": "Astronaut", "start": "2018"}])


class TestYearsOfExperience:
    TODAY = date(2024, 6, 15)

    def years(self, *spans):
        jobs = [{"title": "t", "start": start, "end": end} for start, end in spans]
        return years_of_experience(jobs, today=self.TODAY)

    def test_a_job_counts_from_its_start_to_its_end(self):
        assert self.years(("2014", "2017")) == 4.0

    def test_a_present_job_counts_to_today(self):
        assert self.years(("2022-01", "present")) == 2.5

    def test_overlapping_jobs_are_counted_once(self):
        assert self.years(("2010", "2014"), ("2012", "2016")) == 7.0

    def test_jobs_with_no_start_are_not_counted(self):
        assert self.years((None, "2017")) is None

    def test_a_job_that_ends_before_it_starts_counts_for_its_first_month_only(self):
        assert self.years(("2016", "2012")) == round(1 / 12, 1)


class TestContactDetailsAreSeparate:
    def test_contact_details_are_saved_in_their_own_table(self, cv, ai):
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        contact = CvContact.objects.get(cv_file=cv)
        assert (contact.name, contact.email) == ("Jane Example", "jane@example.com")
        assert contact.phone == "+1 (555) 010-2030"
        assert contact.address == "12 Sample Street, Exampleville"
        assert contact.company_id == cv.company_id

    def test_no_contact_detail_is_in_the_profile(self, cv, ai):
        ai.answers = [answer_with(skills=["Python", "jane@example.com"])]
        saved = profile_reading.read_profile(cv, CV_TEXT)
        text = json.dumps(saved.content)
        for detail in ("Jane Example", "jane@example.com", "555", "Sample Street"):
            assert detail not in text

    def test_a_summary_with_a_contact_detail_is_dropped(self):
        for leak in ("Jane Example is an engineer.", "Write to jane@example.com."):
            profile, _ = check_answer(answer_with(summary=leak), CV_TEXT)
            assert profile["summary"] == ""

    def test_a_contact_detail_not_in_the_cv_is_removed(self):
        contact = {
            "name": "John Invented",
            "email": "john@example.org",
            "phone": "+1 555 999 8888",
            "address": "1 Nowhere Road",
        }
        _, kept = check_answer(answer_with(contact=contact), CV_TEXT)
        assert kept == {"name": "", "email": "", "phone": "", "address": ""}

    def test_a_phone_is_matched_by_its_digits(self):
        _, kept = check_answer(answer_with(contact={"phone": "1-555-010-2030"}), CV_TEXT)
        assert kept["phone"] == "1-555-010-2030"

    def test_a_missing_contact_block_is_fine(self):
        no_contact = {k: v for k, v in GOOD_ANSWER.items() if k != "contact"}
        _, kept = check_answer(json.dumps(no_contact), CV_TEXT)
        assert kept == {"name": "", "email": "", "phone": "", "address": ""}

    def test_nothing_from_the_cv_or_the_answer_is_logged(self, cv, ai, caplog):
        ai.answers = ["jane@example.com is not json", answer_with()]
        with caplog.at_level(logging.DEBUG):
            profile_reading.read_profile(cv, CV_TEXT)
        for line in caplog.text.splitlines():
            assert "jane" not in line.lower() and "555" not in line


class TestAsAStep:
    def run(self, cv, ai, answers):
        ai.answers = answers
        processing.STEPS.clear()
        processing.register_step("ai_reading", profile_reading.read_with_ai)
        processing.register_step("text_reading", lambda context: context.state.update(text=CV_TEXT))
        cv = CvFile.objects.get(pk=cv.pk)
        cv.claim_token = "11111111-1111-1111-1111-111111111111"
        cv.save()
        processing.run_item(CvFile.objects.get(pk=cv.pk))
        return CvFile.objects.get(pk=cv.pk)

    @pytest.fixture(autouse=True)
    def keep_real_steps(self):
        real = dict(processing.STEPS)
        yield
        processing.STEPS.clear()
        processing.STEPS.update(real)

    def test_the_step_is_plugged_into_its_slot(self):
        assert processing.STEPS["ai_reading"] is profile_reading.read_with_ai

    def test_a_cv_with_a_good_answer_is_done_with_a_profile(self, cv, ai):
        finished = self.run(cv, ai, [answer_with()])
        assert finished.status == "done" and CvProfile.objects.filter(cv_file=cv).exists()

    def test_two_bad_answers_fail_the_cv_at_once_with_the_reason_and_it_is_not_counted(
        self, cv, ai
    ):
        finished = self.run(cv, ai, ["x", "y"])
        assert finished.status == "failed"
        assert finished.failure_reason == profile_reading.UNUSABLE_REASON
        assert usage.current_usage(cv.company_id)["cvs_scored"] == 0

    def test_an_unavailable_ai_gives_the_cv_another_try_later(self, cv, ai):
        finished = self.run(cv, ai, [AiUnavailable("down")])
        assert finished.status == "waiting" and finished.attempts == cv.attempts

    def test_retrying_a_failed_cv_reuses_the_saved_profile(self, cv, ai):
        self.run(cv, ai, [answer_with()])
        calls = len(ai.calls)
        self.run(cv, ai, [])
        assert len(ai.calls) == calls


class TestAnotherCompany:
    def test_each_company_gets_its_own_rows_and_its_own_token_count(self, ai):
        first, second = make_cv(), make_cv()
        ai.answers = [answer_with(), answer_with()]
        profile_reading.read_profile(first, CV_TEXT)
        profile_reading.read_profile(second, CV_TEXT)
        for cv in (first, second):
            assert CvProfile.objects.get(cv_file=cv).company_id == cv.company_id
            assert CvContact.objects.get(cv_file=cv).company_id == cv.company_id
            assert usage.current_usage(cv.company_id)["tokens_in"] == 100
        assert CvProfile.objects.filter(company_id=first.company_id).count() == 1


class TestRemoval:
    def test_removing_a_cv_removes_its_profile_and_contact(self, cv, ai, monkeypatch):
        ai.answers = [answer_with()]
        profile_reading.read_profile(cv, CV_TEXT)
        from cvs import service

        monkeypatch.setattr(service.storage, "delete_file", lambda key: None)
        service.remove_cv_file(cv)
        assert not CvProfile.objects.exists() and not CvContact.objects.exists()
