import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from ai.models import AiModel
from cvs import estimate, processing
from cvs.models import CvFile
from cvs.tests.test_ai_reading import set_setting
from cvs.tests.test_processing import Tenant, make_plan
from platform_settings.service import get_setting
from projects.models import Requirement
from projects.service import archive_project
from usage import service as usage

pytestmark = pytest.mark.django_db
HELD = "awaiting_confirmation"


@pytest.fixture
def plan():
    return make_plan()


@pytest.fixture
def tenant(plan):
    return Tenant(plan)


@pytest.fixture
def kicks(monkeypatch):
    asked = []
    monkeypatch.setattr(processing, "async_task", lambda job: asked.append(job))
    return asked


@pytest.fixture(autouse=True)
def known_averages():
    for key, value in {
        "estimate.cv_text_tokens": 1000,
        "estimate.reading_prompt_tokens": 100,
        "estimate.reading_output_tokens": 200,
        "estimate.scoring_prompt_tokens": 50,
        "estimate.scoring_output_tokens_per_requirement": 10,
        "estimate.characters_per_token": 4,
    }.items():
        set_setting(key, value)


def hold(tenant, count=1, batch=None):
    return [tenant.cv(status=HELD, batch=batch) for _ in range(count)]


def add_requirements(project, *texts):
    for position, text in enumerate(texts, 1):
        Requirement.objects.create(
            company_id=project.company_id, project=project, position=position,
            kind="must", text=text, weight=3,
        )  # fmt: skip


def url(tenant):
    return f"/api/company/projects/{tenant.project.pk}/cvs/estimate/"


def shown(tenant, query=""):
    return tenant.client.get(url(tenant) + query).json()


class TestTheEstimate:
    def test_tokens_and_cost_follow_the_settings_and_the_projects_models(self, tenant):
        AiModel.objects.update_or_create(
            name="m",
            defaults={
                "input_price_per_million": Decimal(2),
                "output_price_per_million": Decimal(10),
            },
        )
        AiModel.objects.update_or_create(
            name=get_setting("ai.scoring_model"),
            defaults={
                "input_price_per_million": Decimal(1),
                "output_price_per_million": Decimal(4),
            },
        )
        add_requirements(tenant.project, "8 chars!", "nine char")  # 2 + 3 tokens
        hold(tenant, 2)
        body = shown(tenant)
        # one CV: reading 1100 in, 200 out; scoring 50 + 1000 + 5 in, 2 * 10 out
        assert (body["cvs"], body["tokens_in"], body["tokens_out"]) == (2, 4310, 440)
        assert body["tokens_total"] == 4750
        assert body["estimated_cost"] == "0.010670"  # 2 * (0.0042 + 0.001135)

    def test_it_is_always_marked_approximate(self, tenant):
        assert shown(tenant)["approximate"] is True

    def test_only_held_cvs_are_counted(self, tenant):
        hold(tenant, 2)
        tenant.cv(status="waiting")
        tenant.cv(status="done")
        assert shown(tenant)["cvs"] == 2

    def test_a_batch_can_be_asked_for_on_its_own(self, tenant):
        one, other = uuid.uuid4(), uuid.uuid4()
        hold(tenant, 2, batch=one)
        hold(tenant, 1, batch=other)
        assert shown(tenant, f"?batch={one}")["cvs"] == 2
        assert shown(tenant)["cvs"] == 3

    def test_nothing_held_is_an_estimate_of_zero(self, tenant):
        body = shown(tenant)
        assert (body["cvs"], body["tokens_total"], body["estimated_cost"]) == (0, 0, "0.000000")
        assert body["blocked"] is False

    def test_more_requirements_mean_more_scoring_tokens(self, tenant):
        hold(tenant)
        before = shown(tenant)["tokens_total"]
        add_requirements(tenant.project, "Python", "Django")
        assert shown(tenant)["tokens_total"] > before

    def test_a_model_without_a_price_counts_as_free(self, tenant):
        hold(tenant)
        assert shown(tenant)["estimated_cost"] == "0.000000"

    def test_the_averages_are_platform_settings(self, tenant):
        hold(tenant)
        set_setting("estimate.cv_text_tokens", 2000)
        assert shown(tenant)["tokens_in"] == 100 + 2000 + 50 + 2000


class TestAgainstThePlan:
    def test_it_shows_the_plan_limits_of_cvs_only(self, tenant):
        hold(tenant, 2)
        limits = shown(tenant)["limits"]
        assert limits == {
            "cvs_this_month": {"used": 2, "limit": 100},
            "cvs_in_project": {"used": 2, "limit": 50},
        }

    def test_an_allowed_company_is_not_blocked(self, tenant):
        hold(tenant)
        body = shown(tenant)
        assert (body["blocked"], body["message"], body["prompt"]) == (False, "", None)

    def test_a_large_hold_is_never_blocked_by_tokens(self, tenant, kicks):
        hold(tenant, 3)
        body = shown(tenant)
        assert body["blocked"] is False and "tokens" not in body["limits"]
        assert tenant.confirm().status_code == 200
        assert kicks  # the CVs were released to processing

    def test_an_ended_subscription_is_blocked_with_the_renewal_prompt(self, tenant):
        from plans.models import Subscription

        hold(tenant)
        Subscription.objects.filter(company_id=tenant.company.pk).update(
            renewal=False, period_end=timezone.now() - timezone.timedelta(days=1)
        )
        body = shown(tenant)
        assert (body["blocked"], body["prompt"]) == (True, "renewal")


class TestConfirming:
    def test_confirming_releases_the_held_cvs_and_wakes_the_workers(self, tenant, kicks):
        hold(tenant, 2)
        response = tenant.confirm()
        assert (response.status_code, response.json()) == (200, {"confirmed": 2})
        assert {row.status for row in CvFile.objects.all()} == {"waiting"}
        assert kicks == [processing.TICK_JOB] * 2

    def test_confirming_leaves_other_cvs_alone(self, tenant, kicks):
        hold(tenant)
        done = tenant.cv(status="done")
        tenant.confirm()
        assert CvFile.objects.get(pk=done.pk).status == "done"

    def test_a_batch_is_confirmed_on_its_own(self, tenant, kicks):
        one, other = uuid.uuid4(), uuid.uuid4()
        hold(tenant, 2, batch=one)
        hold(tenant, 1, batch=other)
        assert tenant.confirm(batch=one).json() == {"confirmed": 2}
        assert CvFile.objects.filter(status=HELD).count() == 1

    def test_confirming_twice_does_not_start_anything_twice(self, tenant, kicks):
        hold(tenant)
        assert tenant.confirm().status_code == 200
        second = tenant.confirm()
        assert (second.status_code, second.json()["error"]["code"]) == (409, "nothing_to_confirm")
        assert kicks == [processing.TICK_JOB]

    def test_nothing_held_is_refused_plainly(self, tenant):
        assert tenant.confirm().json()["error"]["code"] == "nothing_to_confirm"

    def test_an_archived_project_cannot_be_confirmed(self, tenant, kicks):
        hold(tenant)
        archive_project(tenant.project.pk, tenant.company.pk)
        assert tenant.confirm().status_code == 409
        assert CvFile.objects.get().status == HELD

    def test_a_held_cv_is_never_picked_up_by_the_workers(self, tenant, kicks):
        hold(tenant)
        assert processing.claim_next() is None

    def test_held_cvs_still_use_their_allowance(self, tenant):
        hold(tenant, 2)
        assert usage.waiting_cvs(tenant.company.pk) == 2


class TestCancelling:
    def test_cancelling_removes_the_held_cvs_and_gives_the_allowance_back(self, tenant, kicks):
        hold(tenant, 2)
        response = tenant.client.post(
            f"/api/company/projects/{tenant.project.pk}/cvs/cancel/", {}, format="json"
        )
        assert response.json() == {"skipped": 2}
        assert {row.status for row in CvFile.objects.all()} == {"cancelled"}
        assert usage.waiting_cvs(tenant.company.pk) == 0

    def test_cancelling_leaves_no_file_behind_and_frees_the_file_s_fingerprint(self, tenant, kicks):
        import privatefiles

        row = hold(tenant)[0]
        privatefiles.save_file(row.storage_key, b"x")
        processing.cancel_unstarted(tenant.project)
        row.refresh_from_db()
        assert row.content_hash is None
        with pytest.raises(privatefiles.StoredFileMissing):
            privatefiles.read_file(row.storage_key)

    def test_a_cancelled_cv_cannot_be_confirmed(self, tenant, kicks):
        hold(tenant)
        processing.cancel_unstarted(tenant.project)
        assert tenant.confirm().json()["error"]["code"] == "nothing_to_confirm"


class TestWhoMayAsk:
    def test_another_companys_project_is_not_found(self, plan, tenant):
        stranger = Tenant(plan)
        hold(stranger)
        for call in (tenant.client.get, tenant.client.post):
            response = call(f"/api/company/projects/{stranger.project.pk}/cvs/estimate/")
            assert response.status_code == 404
        assert CvFile.objects.get().status == HELD

    def test_signed_out_is_refused(self, tenant):
        from rest_framework.test import APIClient

        assert APIClient().get(url(tenant)).status_code == 401
        assert APIClient().post(url(tenant)).status_code == 401


def test_the_estimate_module_is_what_the_view_uses():
    from cvs import views

    assert views.estimate is estimate.estimate and views.confirm is estimate.confirm
