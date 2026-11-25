"""What the API returns and refuses: scopes, one company only, no contact details, and the
upload path that is the panel's own."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apikeys.scopes import CANDIDATES_READ, CVS_UPLOAD, PROJECTS_READ, SCOPES
from apikeys.tests.helpers import API, api_client, end_subscription, make_key, make_tenant
from cvs.models import CvFile, RequirementResult
from cvs.tests.files import make_pdf
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_ranked_list import add
from projects.models import Requirement
from usage import service as usage

pytestmark = pytest.mark.django_db
CONTACT_WORDS = ("jane", "example.com", "phone", "address", "email")


@pytest.fixture
def tenant():
    return make_tenant()


def paths(tenant, candidate_id="00000000-0000-0000-0000-000000000000"):
    project = tenant.project.pk
    return {
        PROJECTS_READ: [("get", f"{API}projects/"), ("get", f"{API}projects/{project}/")],
        CVS_UPLOAD: [("post", f"{API}projects/{project}/cvs/")],
        CANDIDATES_READ: [
            ("get", f"{API}projects/{project}/candidates/"),
            ("get", f"{API}projects/{project}/candidates/{candidate_id}/"),
        ],
    }


def pdf(name="a.pdf", text="Experienced engineer one"):
    return SimpleUploadedFile(name, make_pdf(text=text))


def upload(client, tenant, *files, header=None, **extra):
    extra_headers = {"HTTP_IDEMPOTENCY_KEY": header} if header else {}
    return client.post(
        f"{API}projects/{tenant.project.pk}/cvs/",
        {"files": list(files), **extra},
        format="multipart",
        **extra_headers,
    )


class TestScopes:
    @pytest.mark.parametrize("scope", SCOPES)
    def test_every_route_needs_its_own_scope(self, tenant, scope):
        others = [each for each in SCOPES if each != scope]
        client = api_client(tenant, others)
        for method, address in paths(tenant)[scope]:
            reply = getattr(client, method)(address)
            body = reply.json()["error"]
            assert reply.status_code == 403, address
            assert (body["code"], body["details"]) == ("scope_missing", {"scope": scope})

    @pytest.mark.parametrize("scope", SCOPES)
    def test_a_key_with_only_that_scope_passes_the_door(self, tenant, scope):
        client = api_client(tenant, [scope])
        for method, address in paths(tenant)[scope]:
            reply = getattr(client, method)(address)
            assert reply.status_code != 403 or reply.json()["error"]["code"] != "scope_missing"

    def test_a_scope_never_opens_another_scopes_routes(self, tenant):
        client = api_client(tenant, [PROJECTS_READ])
        assert client.get(f"{API}projects/{tenant.project.pk}/candidates/").status_code == 403
        assert upload(client, tenant, pdf()).status_code == 403


class TestProjects:
    def test_the_list_holds_only_the_keys_company(self, tenant):
        other = make_tenant()
        client = api_client(tenant)
        body = client.get(f"{API}projects/").json()
        assert [each["id"] for each in body["results"]] == [str(tenant.project.pk)]
        assert str(other.project.pk) not in str(body)

    def test_a_bad_query_is_refused_in_the_shared_format(self, tenant):
        reply = api_client(tenant).get(f"{API}projects/", {"sort": "nonsense"})
        assert reply.status_code == 400
        assert reply.json()["error"]["code"] == "validation_error"

    def test_one_project(self, tenant):
        body = api_client(tenant).get(f"{API}projects/{tenant.project.pk}/").json()
        assert body["id"] == str(tenant.project.pk) and "job_description" not in body

    def test_another_companys_project_is_not_found_everywhere(self, tenant):
        other = make_tenant()
        client = api_client(tenant)
        project = other.project.pk
        assert client.get(f"{API}projects/{project}/").status_code == 404
        assert client.get(f"{API}projects/{project}/candidates/").status_code == 404
        assert upload(client, other, pdf()).status_code == 404
        assert not CvFile.objects.filter(company_id=tenant.company.pk).exists()


class TestCandidates:
    @pytest.fixture
    def scored(self, tenant):
        add(tenant, "Jane Example.pdf", 82, ats=70, who="Jane Example")
        add(tenant, "second.pdf", 61, who="Second Person")
        return tenant

    def test_the_ranked_list_has_scores_and_no_names_or_files(self, scored):
        body = api_client(scored).get(f"{API}projects/{scored.project.pk}/candidates/").json()
        assert body["count"] == 2
        first = body["rows"][0]
        assert (first["rank"], first["score"], first["ats_score"]) == (1, "82.0", 70)
        assert {"grade", "label", "stage", "status", "candidate_id"} <= set(first)
        text = str(body).lower()
        assert not any(word in text for word in CONTACT_WORDS + ("second person", ".pdf"))
        assert not {"name", "file_name", "reason"} & set(first)

    def test_it_takes_the_panels_sorting_and_refuses_a_bad_one(self, scored):
        client = api_client(scored)
        address = f"{API}projects/{scored.project.pk}/candidates/"
        ascending = client.get(address, {"sort": "score", "direction": "asc"}).json()["rows"]
        assert [row["score"] for row in ascending] == ["61.0", "82.0"]
        assert client.get(address, {"sort": "contact"}).status_code == 400

    def test_one_candidates_scores_and_requirement_results(self, scored):
        requirement = Requirement.objects.create(
            company=scored.company,
            project=scored.project,
            text="Python",
            kind="must",
            weight=3,
            position=1,
        )
        RequirementResult.objects.create(
            company=scored.company,
            candidate=scored.project.candidates.get(cv_file__original_name="Jane Example.pdf"),
            requirement=requirement,
            requirement_text="Python",
            verdict="met",
            evidence="FAKE-EVIDENCE-QUOTE",
            confidence="high",
            model="m",
            prompt_version=1,
        )
        row = (
            api_client(scored)
            .get(f"{API}projects/{scored.project.pk}/candidates/")
            .json()["rows"][0]
        )
        reply = api_client(scored).get(
            f"{API}projects/{scored.project.pk}/candidates/{row['candidate_id']}/"
        )
        body = reply.json()
        assert body["score"]["grade"] and body["ats_score"] == 70
        assert [(entry["requirement_id"], entry["verdict"]) for entry in body["requirements"]] == [
            (str(requirement.pk), "met")
        ]
        assert "FAKE-EVIDENCE-QUOTE" not in str(body)
        text = str(body).lower()
        assert not any(word in text for word in CONTACT_WORDS)
        for forbidden in ("evidence", "strengths", "risks", "interview_questions", "contact"):
            assert forbidden not in body and forbidden not in str(body["requirements"])

    def test_another_companys_candidate_is_not_found(self, scored):
        other = make_tenant()
        add(other, "theirs.pdf", 90)
        theirs = other.project.candidates.first()
        client = api_client(scored)
        assert (
            client.get(f"{API}projects/{scored.project.pk}/candidates/{theirs.pk}/").status_code
            == 404
        )
        assert (
            client.get(f"{API}projects/{other.project.pk}/candidates/{theirs.pk}/").status_code
            == 404
        )

    def test_a_candidate_of_another_project_of_the_same_company_is_not_found(self, scored):
        from projects.models import Project

        second = Project.objects.create(
            company=scored.company, title="Other", job_description="t", reading_model="m",
            created_by=scored.owner,
        )  # fmt: skip
        candidate = scored.project.candidates.first()
        reply = api_client(scored).get(f"{API}projects/{second.pk}/candidates/{candidate.pk}/")
        assert reply.status_code == 404


class TestUploading:
    def test_it_goes_through_the_panels_path_and_counts_the_same(self, tenant):
        reply = upload(api_client(tenant), tenant, pdf())
        assert reply.status_code == 200
        assert [each["status"] for each in reply.json()["results"]] == ["accepted"]
        stored = CvFile.objects.get()
        assert (stored.company_id, stored.project_id) == (tenant.company.pk, tenant.project.pk)
        assert stored.uploaded_by_id == tenant.owner.pk
        assert usage.waiting_cvs(tenant.company.pk) == 1

    def test_the_file_checks_are_the_same(self, tenant):
        reply = upload(api_client(tenant), tenant, SimpleUploadedFile("a.pdf", b"not really a pdf"))
        assert reply.json()["results"][0]["status"] == "rejected"
        assert not CvFile.objects.exists()

    def test_no_files_is_refused(self, tenant):
        reply = api_client(tenant).post(
            f"{API}projects/{tenant.project.pk}/cvs/", {}, format="multipart"
        )
        assert reply.status_code == 400

    def test_a_batch_over_the_limit_is_refused_whole(self, tenant):
        set_setting("uploads.max_files_per_batch", 2)
        files = [pdf(f"{n}.pdf", f"Different engineer {n}") for n in range(3)]
        reply = upload(api_client(tenant), tenant, *files)
        assert reply.status_code == 400 and reply.json()["error"]["code"] == "too_many_files"
        assert not CvFile.objects.exists()

    def test_the_in_progress_limit_is_the_owners_and_shared_with_the_panel(self, tenant):
        set_setting("uploads.max_files_in_progress_per_user", 1)
        api = api_client(tenant)
        assert upload(api, tenant, pdf("a.pdf", "Engineer a")).status_code == 200
        reply = upload(api, tenant, pdf("b.pdf", "Engineer b"))
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "too_many_in_progress")

    def test_the_monthly_plan_limit_applies(self, tenant):
        from plans.models import Plan

        Plan.objects.update(cvs_per_month=0)
        reply = upload(api_client(tenant), tenant, pdf())
        assert reply.status_code >= 400 or reply.json()["results"][0]["status"] != "accepted"
        assert not CvFile.objects.exists()

    def test_it_is_refused_when_the_subscription_no_longer_allows_the_api(self, tenant):
        api = api_client(tenant)
        end_subscription(tenant.company)
        reply = upload(api, tenant, pdf())
        assert (reply.status_code, reply.json()["error"]["code"]) == (403, "api_access_closed")
        assert not CvFile.objects.exists()

    def test_the_company_upload_rate_limit_applies(self, tenant):
        set_setting("rate_limits.upload_files_per_10_minutes", 1)
        api = api_client(tenant)
        assert upload(api, tenant, pdf("a.pdf", "Engineer a")).status_code == 200
        assert upload(api, tenant, pdf("b.pdf", "Engineer b")).status_code == 429


class TestRepeatedUploads:
    def test_the_same_request_with_the_same_key_is_answered_again_and_not_processed_twice(
        self, tenant
    ):
        api = api_client(tenant)
        first = upload(api, tenant, pdf(), header="request-1")
        again = upload(api, tenant, pdf(), header="request-1")
        assert again.status_code == 200 and again.json() == first.json()
        assert again["Idempotent-Replay"] == "true" and "Idempotent-Replay" not in first
        assert CvFile.objects.count() == 1
        assert usage.waiting_cvs(tenant.company.pk) == 1

    def test_the_same_key_for_different_files_is_refused(self, tenant):
        api = api_client(tenant)
        upload(api, tenant, pdf(), header="request-1")
        reply = upload(api, tenant, pdf("b.pdf", "Another engineer"), header="request-1")
        assert (reply.status_code, reply.json()["error"]["code"]) == (422, "idempotency_key_reused")
        assert CvFile.objects.count() == 1

    def test_the_same_file_under_another_name_is_a_different_request(self, tenant):
        api = api_client(tenant)
        upload(api, tenant, pdf("a.pdf"), header="request-1")
        reply = upload(api, tenant, pdf("renamed.pdf"), header="request-1")
        assert reply.status_code == 422

    def test_a_request_still_running_is_not_started_again(self, tenant):
        from apikeys.models import ApiIdempotency, ApiKey
        from apikeys.uploads import fingerprint_of

        key, token = make_key(tenant)
        from apikeys.tests.helpers import client_with

        sent = pdf()
        ApiIdempotency.objects.create(
            company=tenant.company,
            api_key=key,
            idempotency_key="busy",
            fingerprint=fingerprint_of(tenant.project, None, [sent]),
        )
        reply = upload(client_with(token), tenant, pdf(), header="busy")
        assert (reply.status_code, reply.json()["error"]["code"]) == (409, "request_in_progress")
        assert not CvFile.objects.exists()
        assert ApiKey.objects.count() == 1

    def test_a_refused_request_may_be_tried_again_with_the_same_key(self, tenant):
        set_setting("uploads.max_files_per_batch", 1)
        api = api_client(tenant)
        files = [pdf("a.pdf", "Engineer a"), pdf("b.pdf", "Engineer b")]
        assert upload(api, tenant, *files, header="retry").status_code == 400
        set_setting("uploads.max_files_per_batch", 5)
        files = [pdf("a.pdf", "Engineer a"), pdf("b.pdf", "Engineer b")]
        assert upload(api, tenant, *files, header="retry").status_code == 200
        assert CvFile.objects.count() == 2

    def test_keys_do_not_share_idempotency_keys(self, tenant):
        first, second = api_client(tenant), api_client(tenant)
        upload(first, tenant, pdf(), header="same")
        reply = upload(second, tenant, pdf("b.pdf", "Another engineer"), header="same")
        assert reply.status_code == 200 and "Idempotent-Replay" not in reply

    @pytest.mark.parametrize("value", ["has space", "x" * 65, "bad/char", "ünï"])
    def test_a_bad_idempotency_key_is_refused(self, tenant, value):
        reply = upload(api_client(tenant), tenant, pdf(), header=value)
        assert reply.status_code == 400
        assert not CvFile.objects.exists()

    def test_old_answers_are_forgotten(self, tenant):
        from datetime import timedelta

        from django.utils import timezone

        from apikeys.models import ApiIdempotency

        api = api_client(tenant)
        upload(api, tenant, pdf(), header="old")
        ApiIdempotency.objects.update(created_at=timezone.now() - timedelta(hours=25))
        upload(api, tenant, pdf("b.pdf", "Another engineer"), header="old")
        assert ApiIdempotency.objects.count() == 1


class TestRateLimit:
    def test_each_key_has_its_own_allowance(self, tenant):
        set_setting("rate_limits.api_key_per_minute", 2)
        first, second = api_client(tenant), api_client(tenant)
        answers = [first.get(f"{API}projects/").status_code for _ in range(3)]
        assert answers == [200, 200, 429]
        assert second.get(f"{API}projects/").status_code == 200

    def test_the_wait_is_said_in_plain_words(self, tenant):
        set_setting("rate_limits.api_key_per_minute", 1)
        api = api_client(tenant)
        api.get(f"{API}projects/")
        assert "Try again" in api.get(f"{API}projects/").json()["error"]["message"]
