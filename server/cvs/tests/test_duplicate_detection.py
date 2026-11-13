import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core.errors import AppError
from core.tests.factories import make_company, make_company_user, start_session_for
from cvs import duplicates
from cvs.models import CvFile
from cvs.service import upload_cvs
from cvs.tests.files import make_pdf
from plans import subscriptions as subs
from plans.models import Plan
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache
from projects.models import Project
from usage import service as usage

pytestmark = pytest.mark.django_db


def set_setting(key, value):
    PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})
    clear_cache()


def make_plan(**changes):
    return Plan.objects.create(
        **{
            "name": "Basic",
            "status": "active",
            "price_usd": 10,
            "cvs_per_month": 100,
            "cvs_per_project": 50,
            "max_projects": 5,
            "max_team_accounts": 3,
            "max_top_n": 10,
            "monthly_ai_token_cap": 10000,
            **changes,
        }
    )


@pytest.fixture
def company():
    company = make_company()
    now = timezone.now()
    subs.activate(
        company.pk, make_plan(), period_start=now, period_end=now + timezone.timedelta(days=30)
    )
    return company


@pytest.fixture
def owner(company):
    person = make_company_user(company)
    issued = start_session_for(
        user_id=person.pk, role="owner", company_id=company.pk, kind="company"
    )
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


@pytest.fixture
def project(company, owner):
    return Project.objects.create(
        company=company,
        title="T",
        job_description="t",
        reading_model="m",
        prompt_version="p",
        created_by=owner[0],
    )


def url(project):
    return f"/api/company/projects/{project.pk}/cvs/"


def upload(client, project, *files):
    sent = [SimpleUploadedFile(name, data) for name, data in files]
    return client.post(url(project), {"files": sent}, format="multipart")


def statuses(response):
    return [(r["status"], r["code"]) for r in response.json()["results"]]


def pdf(label):
    return make_pdf(text=f"Experienced engineer {label}")


class TestIdenticalFiles:
    def test_the_same_file_again_is_skipped_with_a_notice_and_not_counted(
        self, company, owner, project, settings
    ):
        _, client = owner
        upload(client, project, ("a.pdf", pdf("one")))
        response = upload(client, project, ("copy.pdf", pdf("one")))
        row = response.json()["results"][0]
        assert (row["status"], row["code"]) == ("skipped", "duplicate_file")
        assert row["message"] == "This file is already in the project, so it was skipped."
        assert CvFile.objects.filter(project=project).count() == 1
        assert usage.waiting_cvs(company.pk) == 1
        stored = [p for p in settings.PRIVATE_FILES_ROOT.rglob("*") if p.is_file()]
        assert len(stored) == 1

    def test_the_name_does_not_matter_only_the_content(self, owner, project):
        _, client = owner
        upload(client, project, ("a.pdf", pdf("one")))
        assert statuses(upload(client, project, ("totally-different-name.pdf", pdf("one")))) == [
            ("skipped", "duplicate_file")
        ]

    def test_a_different_file_is_not_a_repeat(self, owner, project):
        _, client = owner
        upload(client, project, ("a.pdf", pdf("one")))
        assert statuses(upload(client, project, ("a.pdf", pdf("two")))) == [("accepted", "")]

    def test_the_same_file_twice_in_one_upload_is_added_once(self, company, owner, project):
        response = upload(
            owner[1], project, ("a.pdf", pdf("one")), ("b.pdf", pdf("one")), ("c.pdf", pdf("two"))
        )
        assert statuses(response) == [
            ("accepted", ""),
            ("skipped", "duplicate_file"),
            ("accepted", ""),
        ]
        assert usage.waiting_cvs(company.pk) == 2

    def test_a_skipped_file_does_not_use_the_monthly_limit(self, company, owner, project):
        Plan.objects.update(cvs_per_month=2)
        upload(owner[1], project, ("a.pdf", pdf("one")))
        response = upload(
            owner[1],
            project,
            ("copy.pdf", pdf("one")),
            ("b.pdf", pdf("two")),
            ("c.pdf", pdf("three")),
        )
        assert statuses(response) == [
            ("skipped", "duplicate_file"),
            ("accepted", ""),
            ("rejected", "monthly_cv_limit_reached"),
        ]

    def test_the_same_file_in_another_project_is_allowed(self, company, owner, project):
        other = Project.objects.create(
            company=company,
            title="O",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=owner[0],
        )
        upload(owner[1], project, ("a.pdf", pdf("one")))
        assert statuses(upload(owner[1], other, ("a.pdf", pdf("one")))) == [("accepted", "")]

    def test_another_companys_file_is_never_taken_for_a_repeat(self, owner, project):
        stranger = make_company()
        now = timezone.now()
        subs.activate(
            stranger.pk,
            Plan.objects.first(),
            period_start=now,
            period_end=now + timezone.timedelta(days=30),
        )
        theirs_person = make_company_user(stranger)
        issued = start_session_for(
            user_id=theirs_person.pk, role="owner", company_id=stranger.pk, kind="company"
        )
        theirs = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
        their_project = Project.objects.create(
            company=stranger,
            title="T",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=theirs_person,
        )
        upload(theirs, their_project, ("a.pdf", pdf("one")))
        assert statuses(upload(owner[1], project, ("a.pdf", pdf("one")))) == [("accepted", "")]

    def test_only_a_hash_is_kept_not_a_readable_copy(self, owner, project):
        upload(owner[1], project, ("a.pdf", pdf("one")))
        row = CvFile.objects.get(project=project)
        assert row.content_hash == duplicates.content_hash(pdf("one"))
        assert len(row.content_hash) == 64

    def test_the_database_itself_allows_one_copy_per_project(self, company, owner, project):
        from django.db import IntegrityError, transaction

        upload(owner[1], project, ("a.pdf", pdf("one")))
        first = CvFile.objects.get(project=project)
        with pytest.raises(IntegrityError), transaction.atomic():
            CvFile.objects.create(
                company=company,
                project=project,
                original_name="b.pdf",
                file_type="pdf",
                size_bytes=1,
                storage_key="cvs/x/other",
                uploaded_by=owner[0],
                content_hash=first.content_hash,
            )


@pytest.fixture
def two_cvs(company, owner, project):
    """Two CVs of the project, as the processing would have them after upload."""
    upload(owner[1], project, ("a.pdf", pdf("one")), ("b.pdf", pdf("two")))
    first, second = CvFile.objects.filter(project=project).order_by("created_at")
    return first, second


class TestContacts:
    def test_emails_and_phone_numbers_are_found_and_only_hashed(self):
        hashes = duplicates.contact_hashes_in(
            "Jane Doe\nEmail: Jane.Doe@Example.com\nMobile: +1 (555) 010-0100"
        )
        assert len(hashes) == 2
        assert all(len(value) == 64 for value in hashes)
        assert "example" not in "".join(hashes)

    def test_the_same_email_written_differently_gives_the_same_hash(self):
        assert duplicates.contact_hashes_in("JANE@EXAMPLE.COM") == duplicates.contact_hashes_in(
            "contact jane@example.com today"
        )

    def test_the_same_phone_in_other_formats_matches(self):
        a = duplicates.contact_hashes_in("Phone +44 7700 900123")
        b = duplicates.contact_hashes_in("Phone 07700-900-123")
        assert a == b

    @pytest.mark.parametrize("text", ["Year 2019-2023", "ID 12345", "Page 1 of 3", ""])
    def test_short_numbers_and_dates_are_not_phone_numbers(self, text):
        assert duplicates.contact_hashes_in(text) == []

    def test_different_people_have_different_hashes(self):
        assert duplicates.contact_hashes_in("a@example.com") != duplicates.contact_hashes_in(
            "b@example.com"
        )

    def test_the_number_of_digits_compared_comes_from_platform_settings(self):
        set_setting("duplicates.phone_digits", 6)
        assert len(duplicates.contact_hashes_in("Call 555 010")) == 1


class TestLikelySamePerson:
    def test_the_same_email_flags_the_later_cv_for_review(self, two_cvs):
        first, second = two_cvs
        assert duplicates.review_likely_duplicate(first, "Jane jane@example.com") is None
        match = duplicates.review_likely_duplicate(second, "J. Doe, JANE@example.com")
        assert match == first
        second.refresh_from_db()
        first.refresh_from_db()
        assert (second.review, second.duplicate_of_id) == ("flagged", first.pk)
        assert first.review == "none"

    def test_the_same_phone_flags_it_too(self, two_cvs):
        first, second = two_cvs
        duplicates.review_likely_duplicate(first, "Tel +1 555 010 0100")
        assert duplicates.review_likely_duplicate(second, "Phone: 555-010-0100") == first

    def test_different_contacts_are_not_flagged(self, two_cvs):
        first, second = two_cvs
        duplicates.review_likely_duplicate(first, "a@example.com")
        assert duplicates.review_likely_duplicate(second, "b@example.com") is None
        second.refresh_from_db()
        assert second.review == "none"

    def test_a_cv_with_no_contacts_is_never_flagged(self, two_cvs):
        first, second = two_cvs
        duplicates.review_likely_duplicate(first, "no contact here")
        assert duplicates.review_likely_duplicate(second, "nor here") is None

    def test_only_hashes_are_stored(self, two_cvs):
        first, _ = two_cvs
        duplicates.review_likely_duplicate(first, "jane@example.com")
        first.refresh_from_db()
        assert "jane" not in str(first.contact_hashes)
        assert len(first.contact_hashes) == 1

    def test_another_project_or_company_is_not_compared(self, company, owner, project, two_cvs):
        first, second = two_cvs
        other = Project.objects.create(
            company=company,
            title="O",
            job_description="t",
            reading_model="m",
            prompt_version="p",
            created_by=owner[0],
        )
        upload(owner[1], other, ("c.pdf", pdf("three")))
        elsewhere = CvFile.objects.get(project=other)
        duplicates.review_likely_duplicate(first, "jane@example.com")
        assert duplicates.review_likely_duplicate(elsewhere, "jane@example.com") is None

    def test_reading_the_same_cv_again_does_not_flag_it_against_itself(self, two_cvs):
        first, _ = two_cvs
        duplicates.review_likely_duplicate(first, "jane@example.com")
        assert duplicates.review_likely_duplicate(first, "jane@example.com") is None

    def test_a_cv_the_person_kept_is_not_flagged_again(self, two_cvs):
        first, second = two_cvs
        duplicates.review_likely_duplicate(first, "jane@example.com")
        duplicates.review_likely_duplicate(second, "jane@example.com")
        duplicates.keep_flagged_cv(second)
        assert duplicates.review_likely_duplicate(second, "jane@example.com") is None
        second.refresh_from_db()
        assert second.review == "kept"


class TestDecidingAboutAFlaggedCv:
    @pytest.fixture
    def flagged(self, two_cvs):
        first, second = two_cvs
        duplicates.review_likely_duplicate(first, "jane@example.com")
        duplicates.review_likely_duplicate(second, "jane@example.com")
        second.refresh_from_db()
        return first, second

    def test_a_flagged_cv_is_marked_until_decided_and_does_not_count_once_scored(self, flagged):
        _, second = flagged
        assert second.review == "flagged"
        assert duplicates.counts_toward_limits(second) is False

    def test_an_unflagged_cv_counts(self, flagged):
        first, _ = flagged
        assert duplicates.counts_toward_limits(first) is True

    def test_keeping_it_keeps_the_cv_and_lets_it_count(self, company, flagged):
        _, second = flagged
        kept = duplicates.keep_flagged_cv(second)
        assert kept.review == "kept"
        assert duplicates.counts_toward_limits(kept) is True
        assert CvFile.objects.filter(pk=second.pk).exists()

    def test_discarding_it_removes_the_file_and_gives_the_allowance_back(
        self, company, flagged, settings
    ):
        first, second = flagged
        assert usage.waiting_cvs(company.pk) == 2
        duplicates.discard_flagged_cv(second)
        assert not CvFile.objects.filter(pk=second.pk).exists()
        assert CvFile.objects.filter(pk=first.pk).exists()
        assert usage.waiting_cvs(company.pk) == 1
        stored = [p for p in settings.PRIVATE_FILES_ROOT.rglob("*") if p.is_file()]
        assert len(stored) == 1

    def test_a_cv_that_is_not_flagged_cannot_be_kept_or_discarded_this_way(self, two_cvs):
        first, _ = two_cvs
        for decide in (duplicates.keep_flagged_cv, duplicates.discard_flagged_cv):
            with pytest.raises(AppError) as caught:
                decide(first)
            assert caught.value.code == "not_flagged"
        assert CvFile.objects.filter(pk=first.pk).exists()

    def test_deciding_twice_is_refused(self, flagged):
        _, second = flagged
        duplicates.keep_flagged_cv(second)
        with pytest.raises(AppError):
            duplicates.keep_flagged_cv(second)

    def test_an_archived_project_cannot_be_decided_on(self, flagged):
        _, second = flagged
        Project.objects.filter(pk=second.project_id).update(status="archived")
        with pytest.raises(AppError) as caught:
            duplicates.keep_flagged_cv(second)
        assert caught.value.code == "project_archived"

    def test_deleting_the_cv_it_looked_like_keeps_the_flag_without_a_dangling_link(self, flagged):
        first, second = flagged
        from cvs.service import remove_cv_file

        remove_cv_file(first)
        second.refresh_from_db()
        assert second.review == "flagged"
        assert second.duplicate_of_id is None


def test_the_service_function_is_used_by_the_upload(company, owner, project):
    uploader = owner[0]
    files = [("a.pdf", len(pdf("x")), lambda: pdf("x"))]
    assert upload_cvs(uploader, project, files)[0]["status"] == "accepted"
    assert upload_cvs(uploader, project, files)[0]["status"] == "skipped"
