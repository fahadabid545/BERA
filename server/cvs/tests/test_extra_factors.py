from datetime import date

import pytest

from ai import client
from cvs import candidates, extra_factors, processing
from cvs.extra_factors import calculate_factors, refresh_project_factors, store_factors
from cvs.models import CvFile, ExtraFactorValues, RequirementResult
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_candidate_record import add_profile, make_cv
from projects import deletion
from projects.factor_settings import FACTORS
from projects.models import ProjectFactorSettings, Requirement

pytestmark = pytest.mark.django_db
TODAY = date(2024, 6, 15)
JOB = "We need a Backend Engineer who builds services."
GOOD_TEXT = (
    "Experience\nBuilt reliable services for customers across several teams in the company. " * 30
)


def job(title, start, end=None):
    return {"title": title, "start": start, "end": end}


PROFILE = {
    "skills": ["Python"],
    "jobs": [
        job("Senior Backend Engineer", "2018", "present"),
        job("Backend Developer", "2014", "2017"),
    ],
    "years_of_experience": 10.5,
    "education": [{"degree": "MSc Computer Science", "institution": "University of Examples"}],
    "certifications": [],
    "languages": [],
    "summary": "",
}


def make_candidate(profile=None, **config):
    cv = add_profile(make_cv())
    cv.profile.content = PROFILE if profile is None else profile
    cv.profile.save()
    cv.project.job_description = JOB
    cv.project.save()
    if config:
        ProjectFactorSettings.objects.create(
            company_id=cv.company_id,
            project=cv.project,
            factors={name: {"enabled": True, "weight": 50} for name in FACTORS},
            **config,
        )
    return candidates.create_candidate(cv)


def factor(candidate, name, text=GOOD_TEXT):
    return calculate_factors(candidate, text, TODAY)[name]


class TestExperienceYears:
    def test_enough_years_is_a_full_match(self):
        result = factor(make_candidate(required_years=5), "experience_years")
        assert result["value"] == 100 and "10.5 years" in result["explanation"]

    def test_fewer_years_is_in_proportion(self):
        profile = {**PROFILE, "years_of_experience": 2.5}
        assert factor(make_candidate(profile, required_years=5), "experience_years")["value"] == 50

    def test_no_years_needed_is_a_full_match(self):
        assert factor(make_candidate(required_years=0), "experience_years")["value"] == 100

    def test_a_job_with_no_stated_years_is_not_found_not_zero(self):
        result = factor(make_candidate(), "experience_years")
        assert result["value"] is None and result["explanation"].startswith("Not found")

    def test_a_cv_with_no_years_is_not_found_not_zero(self):
        profile = {**PROFILE, "years_of_experience": None}
        result = factor(make_candidate(profile, required_years=5), "experience_years")
        assert result["value"] is None and result["explanation"].startswith("Not found")


class TestEducation:
    @pytest.mark.parametrize(
        ("degree", "needed", "value"),
        [
            ("MSc Computer Science", "bachelor", 100),
            ("MSc Computer Science", "master", 100),
            ("MSc Computer Science", "doctorate", 67),
            ("B.Sc. Physics", "master", 50),
            ("BSc (Hons) Physics", "bachelor", 100),
            ("PhD in Chemistry", "doctorate", 100),
            ("Master of Business Administration", "bachelor", 100),
        ],
    )
    def test_the_highest_level_found_is_compared_with_the_needed_one(self, degree, needed, value):
        profile = {**PROFILE, "education": [{"degree": degree, "institution": ""}]}
        candidate = make_candidate(profile, required_education=needed)
        assert factor(candidate, "education")["value"] == value

    def test_the_highest_of_several_degrees_counts(self):
        profile = {
            **PROFILE,
            "education": [
                {"degree": "BSc Physics", "institution": ""},
                {"degree": "PhD Physics", "institution": ""},
            ],
        }
        assert (
            factor(make_candidate(profile, required_education="doctorate"), "education")["value"]
            == 100
        )

    @pytest.mark.parametrize(
        "education", [[], [{"degree": "Diploma in Welding", "institution": ""}]]
    )
    def test_no_recognised_education_is_not_found_not_zero(self, education):
        profile = {**PROFILE, "education": education}
        result = factor(make_candidate(profile, required_education="bachelor"), "education")
        assert result["value"] is None and result["explanation"].startswith("Not found")

    def test_a_job_with_no_education_need_is_not_found(self):
        assert factor(make_candidate(), "education")["value"] is None

    def test_the_degree_words_are_platform_settings(self):
        set_setting("factors.bachelor_words", ["diploma"])
        profile = {**PROFILE, "education": [{"degree": "Diploma in Welding", "institution": ""}]}
        assert (
            factor(make_candidate(profile, required_education="bachelor"), "education")["value"]
            == 100
        )


class TestSeniority:
    def level(self, title, wanted):
        profile = {**PROFILE, "jobs": [job(title, "2018", "present")]}
        return factor(make_candidate(profile, seniority=wanted), "seniority")

    def test_a_matching_level_is_a_full_match(self):
        assert self.level("Senior Backend Engineer", "senior")["value"] == 100

    @pytest.mark.parametrize(
        ("title", "wanted", "value"),
        [
            ("Backend Engineer", "mid", 100),
            ("Backend Engineer", "senior", 50),
            ("Junior Developer", "lead", 0),
            ("Engineering Manager", "lead", 100),
            ("Principal Engineer", "senior", 50),
            ("Graduate Trainee", "junior", 100),
        ],
    )
    def test_each_step_away_costs_a_platform_setting_amount(self, title, wanted, value):
        assert self.level(title, wanted)["value"] == value

    def test_the_latest_job_decides(self):
        profile = {
            **PROFILE,
            "jobs": [job("Junior Dev", "2010", "2012"), job("Lead Dev", "2020", "present")],
        }
        assert factor(make_candidate(profile, seniority="lead"), "seniority")["value"] == 100

    def test_no_dated_job_is_not_found_not_zero(self):
        profile = {**PROFILE, "jobs": [job("Senior Dev", None, None)]}
        assert factor(make_candidate(profile, seniority="senior"), "seniority")["value"] is None

    def test_a_job_with_no_seniority_is_not_found(self):
        assert factor(make_candidate(), "seniority")["value"] is None


class TestRecency:
    def test_current_relevant_work_is_a_full_match(self):
        assert factor(make_candidate(), "recency")["value"] == 100

    def test_work_that_ended_a_while_ago_fades_by_the_platform_setting(self):
        profile = {**PROFILE, "jobs": [job("Backend Developer", "2018", "2023-06")]}
        result = factor(make_candidate(profile), "recency")
        assert result["value"] == 80 and "12 months ago" in result["explanation"]

    def test_very_old_work_bottoms_out_at_zero_but_is_still_a_found_value(self):
        profile = {**PROFILE, "jobs": [job("Backend Developer", "2000", "2005")]}
        assert factor(make_candidate(profile), "recency")["value"] == 0

    def test_no_job_that_matches_the_description_is_not_found_not_zero(self):
        profile = {**PROFILE, "jobs": [job("Chef", "2018", "present")]}
        result = factor(make_candidate(profile), "recency")
        assert result["value"] is None and result["explanation"].startswith("Not found")

    def test_no_dated_jobs_is_not_found(self):
        profile = {**PROFILE, "jobs": [job("Backend Developer", None, None)]}
        assert factor(make_candidate(profile), "recency")["value"] is None


class TestGapsAndChanges:
    def run(self, jobs):
        return factor(make_candidate({**PROFILE, "jobs": jobs}), "gaps_and_changes")

    def test_an_unbroken_history_is_a_full_match(self):
        result = self.run([job("A", "2015", "2017"), job("B", "2018", "present")])
        assert result["value"] == 100 and "No gaps found" in result["explanation"]

    def test_a_gap_lowers_the_value_and_is_explained_kindly(self):
        result = self.run([job("A", "2015-01", "2016-12"), job("B", "2017-09", "present")])
        assert result["value"] == 80
        assert "1 gap(s) of 6 months or more" in result["explanation"]
        assert "never reject a candidate" in result["explanation"]

    def test_a_gap_just_under_the_limit_is_not_a_gap(self):
        assert (
            self.run([job("A", "2015-01", "2016-12"), job("B", "2017-06", "present")])["value"]
            == 100
        )

    def test_overlapping_jobs_are_not_a_gap(self):
        assert self.run([job("A", "2015", "2019"), job("B", "2018", "present")])["value"] == 100

    def test_frequent_short_jobs_lower_the_value_and_are_explained(self):
        jobs = [
            job("A", "2021-01", "2021-05"),
            job("B", "2021-08", "2022-01"),
            job("C", "2022-03", "2022-09"),
            job("D", "2022-10", "present"),
        ]
        result = self.run(jobs)
        assert "3 short jobs in the last 5 years" in result["explanation"]
        assert result["value"] == 80  # no gaps; three short jobs cost the change penalty

    def test_many_gaps_never_push_the_value_below_zero(self):
        jobs = [job(str(n), f"{2000 + 2 * n}-01", f"{2000 + 2 * n}-03") for n in range(10)]
        assert self.run(jobs)["value"] == 0

    def test_fewer_than_two_dated_jobs_is_not_found_not_zero(self):
        result = self.run([job("A", "2015", "present")])
        assert result["value"] is None and result["explanation"].startswith("Not found")

    def test_the_limits_are_platform_settings(self):
        set_setting("factors.gap_months", 12)
        set_setting("factors.gap_penalty", 50)
        jobs = [job("A", "2015-01", "2015-12"), job("B", "2017-03", "present")]
        assert self.run(jobs)["value"] == 50

    def test_nothing_is_ever_rejected_because_of_gaps(self):
        candidate = make_candidate(
            {
                **PROFILE,
                "jobs": [
                    job(str(n), f"{2000 + 2 * n}-01", f"{2000 + 2 * n}-03") for n in range(10)
                ],
            }
        )
        store_factors(candidate, GOOD_TEXT, TODAY)
        cv = CvFile.objects.get(pk=candidate.cv_file_id)
        assert cv.status != "failed" and cv.review == "none"
        stored = ExtraFactorValues.objects.get(candidate=candidate).values
        assert set(stored["gaps_and_changes"]) == {"value", "explanation"}  # no reject flag at all


class TestReadabilityAndConfidence:
    def test_readability_follows_the_cv_text(self):
        assert factor(make_candidate(), "readability")["value"] == 100
        assert factor(make_candidate(), "readability", text="Hi")["value"] < 100

    def test_no_text_is_not_found_not_zero(self):
        assert factor(make_candidate(), "readability", text="   ")["value"] is None

    def add_results(self, candidate, levels):
        for position, level in enumerate(levels, 1):
            requirement = Requirement.objects.create(
                company_id=candidate.company_id,
                project=candidate.project,
                position=position,
                kind="must",
                text=f"R{position}",
                weight=3,
            )
            RequirementResult.objects.create(
                company_id=candidate.company_id,
                candidate=candidate,
                requirement=requirement,
                requirement_text=requirement.text,
                verdict="missing",
                confidence=level,
                model="m",
                prompt_version=1,
            )

    def test_confidence_is_the_average_of_the_requirement_results(self):
        candidate = make_candidate()
        self.add_results(candidate, ["high", "low"])
        assert factor(candidate, "confidence")["value"] == 60

    def test_the_confidence_values_are_platform_settings(self):
        set_setting("factors.confidence_medium", 10)
        candidate = make_candidate()
        self.add_results(candidate, ["medium"])
        assert factor(candidate, "confidence")["value"] == 10

    def test_no_results_yet_is_not_found_not_zero(self):
        result = factor(make_candidate(), "confidence")
        assert result["value"] is None and result["explanation"].startswith("Not found")


class TestMissingInformationIsNeverZero:
    def test_an_empty_profile_gives_not_found_for_every_factor_that_needs_it(self):
        empty = {"skills": [], "jobs": [], "education": [], "years_of_experience": None}
        candidate = make_candidate(
            empty, required_years=5, required_education="master", seniority="lead"
        )
        values = calculate_factors(candidate, "", TODAY)
        assert set(values) == set(FACTORS)
        for name, result in values.items():
            assert result["value"] is None, name
            assert result["explanation"].startswith("Not found"), name


class TestStoring:
    def test_every_factor_is_stored_even_when_switched_off(self):
        candidate = make_candidate()
        store_factors(candidate, GOOD_TEXT, TODAY)
        stored = ExtraFactorValues.objects.get(candidate=candidate)
        assert set(stored.values) == set(FACTORS) and stored.company_id == candidate.company_id

    def test_storing_again_keeps_one_row(self):
        candidate = make_candidate()
        store_factors(candidate, GOOD_TEXT, TODAY)
        store_factors(candidate, GOOD_TEXT, TODAY)
        assert ExtraFactorValues.objects.count() == 1

    def test_the_same_input_gives_the_same_values(self):
        candidate = make_candidate(required_years=5, seniority="senior")
        assert calculate_factors(candidate, GOOD_TEXT, TODAY) == calculate_factors(
            candidate, GOOD_TEXT, TODAY
        )

    def test_switching_and_weighting_never_change_the_stored_values(self):
        candidate = make_candidate(required_years=5)
        first = calculate_factors(candidate, GOOD_TEXT, TODAY)
        ProjectFactorSettings.objects.filter(project=candidate.project).update(
            factors={name: {"enabled": False, "weight": 0} for name in FACTORS}
        )
        assert calculate_factors(candidate, GOOD_TEXT, TODAY) == first

    def test_a_changed_job_expectation_works_the_values_out_again_from_the_profile(self):
        candidate = make_candidate(required_years=5)
        store_factors(candidate, GOOD_TEXT, TODAY)
        before = ExtraFactorValues.objects.get()
        ProjectFactorSettings.objects.filter(project=candidate.project).update(required_years=20)
        refresh_project_factors(candidate.project)
        after = ExtraFactorValues.objects.get()
        assert before.values["experience_years"]["value"] == 100
        assert after.values["experience_years"]["value"] == 52
        assert after.basis_hash != before.basis_hash
        assert after.values["readability"] == before.values["readability"]  # no text needed

    def test_refreshing_touches_only_the_projects_own_candidates(self):
        mine, theirs = make_candidate(required_years=5), make_candidate(required_years=5)
        store_factors(theirs, GOOD_TEXT, TODAY)
        before = ExtraFactorValues.objects.get(candidate=theirs).updated_at
        refresh_project_factors(mine.project)
        assert ExtraFactorValues.objects.get(candidate=theirs).updated_at == before


class TestAsAStep:
    def test_the_step_is_plugged_in_after_the_ai_evaluation_and_before_scoring(self):
        assert processing.STEPS["extra_factors"] is extra_factors.make_the_factors
        slots = processing.SLOTS
        assert slots.index("requirement_evaluation") < slots.index("extra_factors")
        assert slots.index("extra_factors") < slots.index("scoring")

    def test_the_step_stores_the_factors_from_the_original_text(self):
        candidate = make_candidate()
        cv = CvFile.objects.get(pk=candidate.cv_file_id)
        context = processing.StepContext(cv, cv.company_id, cv.project_id, {"text": GOOD_TEXT})
        extra_factors.make_the_factors(context)
        assert (
            ExtraFactorValues.objects.get(candidate=candidate).values["readability"]["value"] == 100
        )

    def test_it_never_calls_the_ai(self, monkeypatch):
        monkeypatch.setattr(client, "_send", lambda **call: pytest.fail("the AI was called"))
        store_factors(make_candidate(required_years=5), GOOD_TEXT, TODAY)


class TestRemoval:
    def test_removing_the_candidate_removes_the_values(self):
        candidate = make_candidate()
        store_factors(candidate, GOOD_TEXT, TODAY)
        candidates.remove_candidate(candidate)
        assert not ExtraFactorValues.objects.exists()

    def test_deleting_the_project_removes_values_and_settings(self):
        candidate = make_candidate(required_years=5)
        store_factors(candidate, GOOD_TEXT, TODAY)
        deletion.delete_project(candidate.cv_file.uploaded_by, candidate.project)
        assert not ExtraFactorValues.objects.exists()
        assert not ProjectFactorSettings.objects.exists()


class TestAnotherCompany:
    def test_values_belong_to_their_own_company(self):
        mine, theirs = make_candidate(), make_candidate()
        store_factors(mine, GOOD_TEXT, TODAY)
        store_factors(theirs, GOOD_TEXT, TODAY)
        assert ExtraFactorValues.objects.get(candidate=mine).company_id == mine.company_id
        deletion.delete_project(mine.cv_file.uploaded_by, mine.project)
        assert ExtraFactorValues.objects.get().company_id == theirs.company_id
