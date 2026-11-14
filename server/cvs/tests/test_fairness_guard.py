import pytest

from core.tests.factories import make_company, make_company_user
from cvs import fairness, processing
from cvs.fairness import remove_personal_details
from cvs.models import CvContact, CvFile
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project

pytestmark = pytest.mark.django_db

JANE = {
    "name": "Jane Example",
    "email": "jane@example.com",
    "phone": "+1 (555) 010-2030",
    "address": "12 Sample Street, Exampleville",
}

# Each sample: (text, contact, details that must not survive, facts that must survive).
SAMPLES = {
    "header block": (
        "Jane Example\nPhoto: jane.jpg\nDate of birth: 03/05/1990\nGender: Female\n"
        "Marital status: Married\nNationality: Examplian\nReligion: Examplism\n"
        "Address: 12 Sample Street, Exampleville\nEmail: jane@example.com\n"
        "Phone: +1 (555) 010-2030\n\nExperience\nBackend Developer, 2014 - 2017\n"
        "Skills: Python, Go",
        JANE,
        [
            "Jane",
            "Example",
            "03/05/1990",
            "Female",
            "Married",
            "Examplian",
            "Examplism",
            "Sample Street",
            "jane@",
            "555",
            "jane.jpg",
        ],
        ["Backend Developer, 2014 - 2017", "Skills: Python, Go"],
    ),
    "one line with separators": (
        "CV | Age: 34 | Nationality: Examplian | Marital status: Single | jane@example.com\n"
        "Engineer at Acme, 2018 - present",
        JANE,
        ["34", "Examplian", "Single", "jane@"],
        ["Engineer at Acme, 2018 - present"],
    ),
    "page footer and middle of text": (
        "Led a team of five engineers.\nJane Example led the migration to PostgreSQL.\n"
        "Reach me on 555-010-2030 or jane@example.com about it.\n\f"
        "Page 2 of 2 - Jane Example - jane@example.com - +1 555 010 2030\n",
        JANE,
        ["Jane", "jane@", "555"],
        ["Led a team of five engineers.", "led the migration to PostgreSQL."],
    ),
    "table with values on the next line": (
        "Personal details\nNationality\nExamplian\nDate of birth\n3 May 1990\nSkills\nPython",
        None,
        ["Examplian", "3 May 1990"],
        ["Personal details", "Skills", "Python"],
    ),
    "born and age without labels": (
        "I was born on 3rd May 1990 and moved to the city.\nAge 34\nDOB 12.05.1990\n"
        "Built the billing system.",
        None,
        ["1990", "34"],
        ["moved to the city.", "Built the billing system."],
    ),
    "bulleted list": (
        "• Gender: Male\n- Religion: Examplism\n* Nationality: Examplian\nRole: Data Analyst",
        None,
        ["Male", "Examplism", "Examplian"],
        ["Role: Data Analyst"],
    ),
}


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


class TestSampleCvsSendNoPersonalDetailsToScoring:
    @pytest.mark.parametrize("sample", SAMPLES)
    def test_none_of_the_details_remain_and_the_work_history_does(self, sample):
        text, contact, forbidden, required = SAMPLES[sample]
        result = remove_personal_details(text, contact)
        for detail in forbidden:
            assert detail.lower() not in result.lower(), (detail, result)
        for fact in required:
            assert fact in result, (fact, result)


class TestKnownValues:
    def test_the_name_is_removed_in_any_case_and_each_part_alone(self):
        result = remove_personal_details("JANE EXAMPLE joined. Jane then left. example", JANE)
        assert "jane" not in result.lower() and "example" not in result.lower()

    def test_short_name_parts_are_kept_so_ordinary_words_stay(self):
        contact = {"name": "Li Wei Chen"}
        result = remove_personal_details("Li Wei Chen built it. Wei is an Li-ion expert", contact)
        assert "Chen" not in result and "Wei" not in result
        assert "Li-ion" in result

    def test_the_minimum_name_part_length_is_a_platform_setting(self):
        set_setting("fairness.min_name_part_length", 2)
        assert "Li" not in remove_personal_details("Li did it", {"name": "Li Wei"})

    def test_the_address_is_removed_however_its_lines_are_written(self):
        text = "Home\n12 Sample\nStreet\nExampleville\nSkills: Python"
        assert "Sample" not in remove_personal_details(text, JANE)
        assert "Exampleville" not in remove_personal_details(
            "12 Sample Street,\nExampleville", JANE
        )

    def test_a_phone_is_found_in_any_format(self):
        for written in ("+15550102030", "1 555 010 2030", "(555) 010-2030", "+1.555.010.2030"):
            assert "010" not in remove_personal_details(f"Call {written} now", JANE)

    def test_an_email_is_found_in_any_case(self):
        assert "example.com" not in remove_personal_details("Mail JANE@Example.COM today", JANE)

    def test_a_contact_given_as_an_object_works_like_a_dict(self):
        contact = CvContact(**JANE)
        assert "Jane" not in remove_personal_details("Jane Example", contact)

    def test_no_contact_record_still_removes_what_the_patterns_find(self):
        assert "@" not in remove_personal_details("Write to a.b@example.org please", None)


class TestPatterns:
    def test_any_email_and_phone_is_removed_even_when_it_is_not_the_cvs_own(self):
        result = remove_personal_details(
            "Referee: ann@example.org, +44 20 7946 0958, 020 7946 0958", JANE
        )
        assert "@" not in result and "7946" not in result

    def test_ranges_of_years_and_versions_are_not_phone_numbers(self):
        text = "Developer 2014 - 2017, Python 3.12, built 2018-2020, Windows 10.0.19045"
        assert remove_personal_details(text, None) == text

    def test_a_date_after_born_is_removed_in_common_forms(self):
        for born in (
            "born 1990",
            "Born: 3 May 1990",
            "born on May 3, 1990",
            "born in 03-05-1990",
        ):
            assert "1990" not in remove_personal_details(f"I was {born}, and then worked.", None)

    def test_born_without_a_date_is_left_alone(self):
        assert "born" in remove_personal_details("A born leader.", None)

    def test_the_born_words_are_a_platform_setting(self):
        set_setting("fairness.born_words", ["born", "geboren"])
        assert "1990" not in remove_personal_details("geboren 1990", None)


class TestLabels:
    def test_a_label_in_the_middle_of_a_sentence_is_not_cut(self):
        text = "The project name: Atlas. We improved the age of the data model."
        assert remove_personal_details(text, None) == text

    def test_words_that_look_like_nationality_or_religion_are_left_alone(self):
        text = "Opened Indian cuisine restaurant. Worked at Christian Aid and Muslim Hands."
        assert remove_personal_details(text, None) == text

    def test_labels_are_matched_in_any_case(self):
        assert "Male" not in remove_personal_details("GENDER: Male", None)

    def test_the_labels_are_a_platform_setting(self):
        set_setting("fairness.labels", ["nationality"])
        result = remove_personal_details("Gender: Male\nNationality: Examplian", None)
        assert "Male" in result and "Examplian" not in result

    def test_a_label_with_no_value_and_no_next_line_is_removed_without_error(self):
        assert remove_personal_details("Skills: Go\nGender:", None) == "Skills: Go"

    def test_only_the_label_part_of_a_separated_line_is_removed(self):
        result = remove_personal_details("Python | Gender: Male | Django", None)
        assert result == "Python | Django"


class TestOutput:
    def test_lines_without_details_come_back_unchanged(self):
        text = "Senior Engineer\n\nBuilt things.\n  Indented line\n"
        assert remove_personal_details(text, JANE) == text

    def test_a_line_that_only_held_a_detail_is_dropped(self):
        assert remove_personal_details("Skills\nGender: Male\nPython", None) == "Skills\nPython"

    def test_empty_text_is_fine(self):
        assert remove_personal_details("", JANE) == ""

    def test_the_input_is_not_changed_and_the_marker_is_not_left_behind(self):
        text = "a\x00b Jane Example"
        result = remove_personal_details(text, JANE)
        assert "\x00" not in result and text == "a\x00b Jane Example"

    def test_a_big_text_is_handled_quickly(self):
        text = ("Built services in Python. " * 20 + "\n") * 2000
        assert remove_personal_details(text, JANE)


class TestAsAStep:
    @pytest.fixture
    def cv(self):
        company = make_company()
        owner = make_company_user(company)
        project = Project.objects.create(
            company=company,
            title="T",
            job_description="t",
            reading_model="m",
            created_by=owner,
        )
        return CvFile.objects.create(
            company=company,
            project=project,
            original_name="cv.pdf",
            file_type="pdf",
            size_bytes=1,
            storage_key=f"cvs/{company.pk}/x",
            uploaded_by=owner,
        )

    def context(self, cv, text):
        return processing.StepContext(cv, cv.company_id, cv.project_id, {"text": text})

    def test_the_step_is_plugged_into_its_slot(self):
        assert processing.STEPS["fairness_guard"] is fairness.guard_the_text

    def test_the_step_keeps_the_original_text_and_adds_the_guarded_text(self, cv):
        CvContact.objects.create(company_id=cv.company_id, cv_file=cv, **JANE)
        context = self.context(cv, "Jane Example\nBuilt services in Python.")
        fairness.guard_the_text(context)
        assert context.state["scoring_text"] == "Built services in Python."
        assert "Jane" in context.state["text"]

    def test_the_step_works_for_a_cv_with_no_contact_record(self, cv):
        context = self.context(cv, "Gender: Male\nBuilt services in Python.")
        fairness.guard_the_text(context)
        assert context.state["scoring_text"] == "Built services in Python."

    def test_another_companys_contact_is_never_used(self, cv):
        other = make_company()
        other_owner = make_company_user(other)
        other_project = Project.objects.create(
            company=other,
            title="T",
            job_description="t",
            reading_model="m",
            created_by=other_owner,
        )
        other_cv = CvFile.objects.create(
            company=other,
            project=other_project,
            original_name="cv.pdf",
            file_type="pdf",
            size_bytes=1,
            storage_key=f"cvs/{other.pk}/x",
            uploaded_by=other_owner,
        )
        CvContact.objects.create(company_id=other.pk, cv_file=other_cv, name="Zed Other")
        context = self.context(cv, "Zed Other built it.")
        fairness.guard_the_text(context)
        assert "Zed" in context.state["scoring_text"]
