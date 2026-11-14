import pytest
from django.db import IntegrityError, transaction

from ai import client
from cvs import ats, ats_layout, ats_scoring, candidates, processing
from cvs.ats import Layout, job_keywords, score_cv
from cvs.models import AtsScore, CvFile
from cvs.tests.files import make_docx, make_pdf
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_candidate_record import add_profile, make_cv
from projects import deletion

pytestmark = pytest.mark.django_db

JOB = (
    "We need a Senior Backend Engineer with strong Python, Django and PostgreSQL experience. "
    "You will build REST APIs, write Docker containers and deploy to AWS. "
    "Python and Django are essential."
)
FILLER = (
    "Designed and operated reliable services for a large customer base and mentored colleagues "
    "while improving release quality and monitoring across several teams in the company. "
) * 8

GOOD_CV = f"""Jane Example
jane@example.com +1 555 010 2030

Experience
Senior Backend Engineer, 2018 - present
Built REST APIs in Python and Django on PostgreSQL, packaged in Docker containers.
Write clean code and deploy it to AWS every week.
{FILLER}

Education
BSc Computer Science, University of Examples

Skills
Python, Django, PostgreSQL, Docker, AWS
"""
BARE_CV = "Jane Example. I like computers and I have worked with them for a long time."
ICON_LINE = " \ue000 ".join("Python Django Docker AWS PostgreSQL REST engineer".split())
ICON_CV = "\n".join(
    ["\ue000 Jane Example", "\ue001 jane@example.com", "Experience", "Skills", "Education"]
    + [ICON_LINE + " and more of the same work in the company"] * 12
)


class TestKeywords:
    def test_the_job_descriptions_most_frequent_words_come_first_without_common_words(self):
        words = job_keywords(JOB)
        assert words[:5] == ["python", "django", "senior", "backend", "engineer"]
        assert "the" not in words and "experience" not in words and "essential" not in words
        assert "api" in words and "container" in words  # plurals are matched to the singular

    def test_numbers_and_one_letter_words_are_not_keywords(self):
        assert job_keywords("5 years of 10 x") == []

    def test_the_number_of_keywords_is_a_platform_setting(self):
        set_setting("ats.keyword_count", 3)
        assert job_keywords(JOB) == ["python", "django", "senior"]

    def test_the_same_description_always_gives_the_same_list(self):
        assert job_keywords(JOB) == job_keywords(JOB)

    def test_skills_with_symbols_are_kept_whole(self):
        assert "c++" in job_keywords("C++ and C# and .NET developer") or "c#" in job_keywords(
            "C++ and C# developer"
        )


class TestKeywordPart:
    def test_a_cv_with_every_keyword_loses_nothing_for_keywords(self):
        result = score_cv(GOOD_CV, JOB)
        assert not [r for r in result.reasons if r.code == "keywords_missing"]

    def test_a_cv_with_none_loses_the_whole_keyword_share_and_lists_some_missing_words(self):
        result = score_cv("Gardening and cooking are my hobbies.", JOB)
        reason = next(r for r in result.reasons if r.code == "keywords_missing")
        assert "such as python, django, senior, backend, engineer" in reason.message
        assert reason.points == 40.0

    def test_partial_matches_lose_a_part(self):
        reason = next(
            r for r in score_cv("python django", JOB).reasons if r.code == "keywords_missing"
        )
        assert 0 < reason.points < 40

    def test_a_description_with_no_keywords_cannot_lower_the_score(self):
        assert not [r for r in score_cv(GOOD_CV, "to be").reasons if r.code == "keywords_missing"]

    def test_how_many_missing_words_are_listed_is_a_platform_setting(self):
        set_setting("ats.keywords_listed", 2)
        reason = next(r for r in score_cv("nothing", JOB).reasons if r.code == "keywords_missing")
        assert reason.message.endswith("such as python, django.")


class TestSections:
    def codes(self, text):
        return {r.code for r in score_cv(text, "").reasons}

    def test_a_cv_with_every_section_is_complete(self):
        assert not self.codes(GOOD_CV) & {
            "contact_missing",
            "experience_missing",
            "education_missing",
            "skills_missing",
        }

    def test_each_missing_section_is_a_reason(self):
        assert {
            "contact_missing",
            "experience_missing",
            "education_missing",
            "skills_missing",
        } <= self.codes(BARE_CV)

    def test_a_phone_number_alone_is_contact_enough(self):
        assert "contact_missing" not in self.codes("Call +44 20 7946 0958\nSkills\nEducation")

    @pytest.mark.parametrize(
        "heading", ["EXPERIENCE", "Work Experience:", "  Professional Experience  ", "Employment"]
    )
    def test_headings_are_found_whatever_the_case_and_punctuation(self, heading):
        assert "experience_missing" not in self.codes(f"{heading}\nBuilt things")

    def test_a_sentence_that_mentions_a_section_word_is_not_a_heading(self):
        text = "I have a lot of experience building skills and education programmes in the company"
        assert {"experience_missing", "skills_missing", "education_missing"} <= self.codes(text)

    def test_the_headings_are_platform_settings(self):
        set_setting("ats.skills_headings", ["abilities"])
        assert "skills_missing" in self.codes("Skills\nPython")
        assert "skills_missing" not in self.codes("Abilities\nPython")


class TestReadability:
    def codes(self, text):
        return {r.code for r in score_cv(text, "").reasons}

    def test_a_normal_cv_reads_well(self):
        assert not self.codes(GOOD_CV) & {
            "text_too_short",
            "text_too_long",
            "unreadable_characters",
            "broken_lines",
        }

    def test_very_little_text_is_flagged(self):
        assert "text_too_short" in self.codes(BARE_CV)

    def test_far_too_much_text_is_flagged(self):
        assert "text_too_long" in self.codes("Built systems for customers and users. " * 400)

    def test_icon_font_symbols_are_flagged(self):
        assert "unreadable_characters" in self.codes(ICON_CV)

    def test_one_word_per_line_text_is_flagged(self):
        assert "broken_lines" in self.codes("\n".join(["Python"] * 300))

    def test_the_limits_are_platform_settings(self):
        set_setting("ats.min_words", 5)
        assert "text_too_short" not in self.codes(BARE_CV)


class TestFormatting:
    def test_no_layout_information_means_no_formatting_problem(self):
        assert not {r.code for r in score_cv(GOOD_CV, JOB).reasons} & {
            "text_in_images",
            "too_many_pages",
        }

    def test_pages_that_are_pictures_of_text_are_flagged(self):
        codes = {
            r.code for r in score_cv(GOOD_CV, JOB, Layout(page_count=1, image_pages=1)).reasons
        }
        assert "text_in_images" in codes

    def test_too_many_pages_are_flagged_and_the_limit_is_a_platform_setting(self):
        assert "too_many_pages" in {
            r.code for r in score_cv(GOOD_CV, JOB, Layout(page_count=4)).reasons
        }
        set_setting("ats.max_pages", 5)
        assert "too_many_pages" not in {
            r.code for r in score_cv(GOOD_CV, JOB, Layout(page_count=4)).reasons
        }


class TestLayoutOfRealFiles:
    def test_a_text_pdf_has_no_picture_pages(self):
        layout = ats_layout.layout_of("pdf", make_pdf(pages=2), 2)
        assert (layout.page_count, layout.image_pages) == (2, 0)

    def test_a_page_that_is_a_picture_with_hardly_any_text_is_found(self):
        data = make_pdf(pages=2, text="Hi", image_on_pages=(1,))
        layout = ats_layout.layout_of("pdf", data, 2)
        assert (layout.page_count, layout.image_pages) == (2, 1)

    def test_a_page_with_a_picture_and_plenty_of_text_is_not_a_picture_page(self):
        data = make_pdf(text="Experienced backend engineer " * 6, image_on_pages=(0,))
        assert ats_layout.layout_of("pdf", data, 1).image_pages == 0

    def test_a_word_file_has_no_picture_pages_and_keeps_the_page_count(self):
        assert ats_layout.layout_of("docx", make_docx(), 2) == Layout(page_count=2)

    def test_an_unreadable_pdf_reports_nothing_special(self):
        assert ats_layout.layout_of("pdf", b"not a pdf", 3) == Layout(page_count=3)


class TestTheScore:
    def test_a_complete_cv_scores_high_and_a_bare_one_low(self):
        good, bare = score_cv(GOOD_CV, JOB), score_cv(BARE_CV, JOB)
        assert good.score == 100 and good.reasons == []
        assert bare.score < 30

    def test_sample_cvs_get_stable_scores_with_reasons(self):
        samples = {
            "good": (GOOD_CV, Layout(page_count=2), 100, []),
            "bare": (
                BARE_CV,
                Layout(page_count=1),
                26,
                [
                    "keywords_missing",
                    "contact_missing",
                    "experience_missing",
                    "education_missing",
                    "skills_missing",
                ],
            ),
            "icons_and_images": (
                ICON_CV,
                Layout(page_count=5, image_pages=1),
                63,
                ["keywords_missing", "text_in_images", "too_many_pages", "unreadable_characters"],
            ),
        }
        for name, (text, layout, score, codes) in samples.items():
            for _ in range(3):
                result = score_cv(text, JOB, layout)
                assert result.score == score, name
                assert [r.code for r in result.reasons][: len(codes)] == codes, name

    def test_the_same_input_always_gives_the_same_result(self):
        runs = [score_cv(BARE_CV, JOB, Layout(page_count=1)) for _ in range(5)]
        assert all(run == runs[0] for run in runs)

    def test_the_reasons_come_largest_loss_first_and_are_capped(self):
        result = score_cv(BARE_CV, JOB)
        points = [reason.points for reason in result.reasons]
        assert points == sorted(points, reverse=True) and all(point > 0 for point in points)
        set_setting("ats.reasons_shown", 2)
        assert len(score_cv(BARE_CV, JOB).reasons) == 2

    def test_the_weights_are_platform_settings(self):
        set_setting("ats.weight_keywords", 0)
        set_setting("ats.weight_sections", 0)
        set_setting("ats.weight_readability", 0)
        set_setting("ats.weight_formatting", 10)
        assert score_cv(BARE_CV, JOB, Layout(page_count=1)).score == 100
        assert score_cv(BARE_CV, JOB, Layout(page_count=9)).score == 50

    def test_all_weights_at_zero_does_not_break(self):
        for name in ("keywords", "sections", "readability", "formatting"):
            set_setting(f"ats.weight_{name}", 0)
        assert score_cv(GOOD_CV, JOB).score == 0

    def test_empty_text_is_fine(self):
        assert 0 <= score_cv("", JOB).score <= 100

    def test_the_reasons_name_no_personal_detail(self):
        text = "Zelda Quillfeather zelda@sentinel.example +1 555 010 7788\n" + BARE_CV
        shown = " ".join(reason.message for reason in score_cv(text, JOB).reasons)
        for detail in ("Zelda", "Quillfeather", "sentinel", "7788"):
            assert detail not in shown

    def test_the_result_is_a_whole_number_from_0_to_100(self):
        for text in (GOOD_CV, BARE_CV, ICON_CV, ""):
            assert isinstance(score_cv(text, JOB).score, int)
            assert 0 <= score_cv(text, JOB).score <= 100


@pytest.fixture
def candidate():
    cv = add_profile(make_cv())
    cv.project.job_description = JOB
    cv.project.save()
    return candidates.create_candidate(cv)


class TestSavedScore:
    def test_the_score_is_saved_with_its_reasons_and_rules_version(self, candidate):
        saved = ats_scoring.calculate_ats_score(candidate, BARE_CV, make_pdf())
        assert saved.score == score_cv(BARE_CV, JOB, Layout(page_count=1)).score
        assert saved.reasons[0]["code"] == "keywords_missing"
        assert set(saved.reasons[0]) == {"code", "message", "points"}
        assert saved.rules_version == ats.RULES_VERSION
        assert saved.company_id == candidate.company_id

    def test_an_unchanged_job_description_keeps_the_stored_score(self, candidate, monkeypatch):
        first = ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        monkeypatch.setattr(ats_scoring, "score_cv", lambda *a, **k: pytest.fail("recalculated"))
        again = ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        assert again.pk == first.pk and AtsScore.objects.count() == 1

    def test_an_edited_job_description_is_measured_again(self, candidate):
        first = ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        candidate.project.job_description = "We need a gardener who knows roses and tulips."
        candidate.project.save()
        again = ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        assert again.pk == first.pk and again.score != first.score
        assert AtsScore.objects.count() == 1

    def test_a_score_made_by_older_rules_is_made_again(self, candidate):
        ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        AtsScore.objects.update(rules_version=ats.RULES_VERSION - 1)
        assert ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf()).rules_version == (
            ats.RULES_VERSION
        )

    def test_the_picture_pages_of_the_file_lower_the_stored_score(self, candidate):
        plain = ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf(text="Hi"))
        AtsScore.objects.all().delete()
        pictured = ats_scoring.calculate_ats_score(
            candidate, GOOD_CV, make_pdf(text="Hi", image_on_pages=(0,))
        )
        assert pictured.score < plain.score
        assert "text_in_images" in [r["code"] for r in pictured.reasons]

    def test_the_database_refuses_a_score_over_100(self, candidate):
        with pytest.raises(IntegrityError), transaction.atomic():
            AtsScore.objects.create(
                company_id=candidate.company_id,
                candidate=candidate,
                score=101,
                job_description_hash="x",
                rules_version=1,
            )


class TestWithoutAi:
    def test_it_never_calls_the_ai(self, candidate, monkeypatch):
        monkeypatch.setattr(client, "_send", lambda **call: pytest.fail("the AI was called"))
        ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())

    def test_it_is_separate_from_the_ai_score(self):
        import inspect

        from cvs import evaluation

        assert "ats" not in inspect.getsource(evaluation).lower().replace("stats", "")
        assert {f.name for f in AtsScore._meta.get_fields()}.isdisjoint({"verdict", "evidence"})


class TestAsAStep:
    def context(self, candidate, text=GOOD_CV, data=None):
        cv = CvFile.objects.get(pk=candidate.cv_file_id)
        return processing.StepContext(
            cv, cv.company_id, cv.project_id, {"text": text, "file_data": data or make_pdf()}
        )

    def test_the_step_is_plugged_into_its_slot_before_the_ai_evaluation(self):
        assert processing.STEPS["ats_score"] is ats_scoring.score_for_ats
        slots = processing.SLOTS
        assert slots.index("candidate_record") < slots.index("ats_score")
        assert slots.index("ats_score") < slots.index("requirement_evaluation")

    def test_the_step_judges_the_original_text_so_the_contact_details_count(self, candidate):
        ats_scoring.score_for_ats(self.context(candidate))
        reasons = [r["code"] for r in AtsScore.objects.get().reasons]
        assert "contact_missing" not in reasons

    def test_a_cv_goes_through_the_slot_and_gets_its_score(self, candidate):
        real = dict(processing.STEPS)
        processing.STEPS.clear()
        processing.register_step("ats_score", ats_scoring.score_for_ats)
        try:
            processing.STEPS["text_reading"] = lambda c: c.state.update(
                text=GOOD_CV, file_data=make_pdf()
            )
            row = CvFile.objects.get(pk=candidate.cv_file_id)
            row.claim_token = "11111111-1111-1111-1111-111111111111"
            row.save()
            processing.run_item(CvFile.objects.get(pk=row.pk))
        finally:
            processing.STEPS.clear()
            processing.STEPS.update(real)
        assert CvFile.objects.get(pk=row.pk).status == "done"
        assert AtsScore.objects.get().score == 100


class TestRemoval:
    def test_removing_the_candidate_removes_the_score(self, candidate):
        ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        candidates.remove_candidate(candidate)
        assert not AtsScore.objects.exists()

    def test_deleting_the_project_removes_the_score(self, candidate):
        ats_scoring.calculate_ats_score(candidate, GOOD_CV, make_pdf())
        deletion.delete_project(candidate.cv_file.uploaded_by, candidate.project)
        assert not AtsScore.objects.exists()


class TestAnotherCompany:
    def test_a_score_belongs_to_its_own_company(self):
        mine = candidates.create_candidate(add_profile(make_cv()))
        theirs = candidates.create_candidate(add_profile(make_cv()))
        ats_scoring.calculate_ats_score(mine, GOOD_CV, make_pdf())
        ats_scoring.calculate_ats_score(theirs, BARE_CV, make_pdf())
        assert AtsScore.objects.get(candidate=mine).company_id == mine.company_id
        assert AtsScore.objects.filter(company_id=mine.company_id).count() == 1
        deletion.delete_project(mine.cv_file.uploaded_by, mine.project)
        assert AtsScore.objects.get().company_id == theirs.company_id
