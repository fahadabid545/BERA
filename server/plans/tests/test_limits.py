import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from companies.invites import invite_member
from core.errors import AppError
from core.tests.factories import make_company, make_company_user
from plans import limits
from plans import subscriptions as subs
from plans.models import LimitOverride, Plan
from platform_settings.service import get_setting
from usage import service as usage

pytestmark = pytest.mark.django_db
DAY = timedelta(days=1)

LIMITS = {
    "cvs_per_month": 5,
    "cvs_per_project": 3,
    "max_projects": 2,
    "max_team_accounts": 2,
    "max_top_n": 10,
    "monthly_ai_token_cap": 1000,
}


def make_plan(name="Basic", usd="10", **changes):
    return Plan.objects.create(
        name=name, status="active", price_usd=Decimal(usd), **{**LIMITS, **changes}
    )


def subscribe(company, plan, days=30):
    now = timezone.now()
    subs.activate(company.pk, plan, period_start=now, period_end=now + days * DAY)


@pytest.fixture
def plan():
    return make_plan()


@pytest.fixture
def top_plan(plan):
    return make_plan("Top", usd="50")


@pytest.fixture
def company(plan, top_plan):
    company = make_company()
    make_company_user(company, role="owner")
    subscribe(company, plan)
    return company


def score(company, count=1, project=None):
    for _ in range(count):
        cv = uuid.uuid4()
        usage.accept_cv(company.pk, cv, project)
        usage.mark_scored(company.pk, cv)


class TestReadingLimits:
    @pytest.mark.parametrize("name", limits.LIMIT_NAMES)
    def test_the_plans_value_is_used(self, company, name):
        assert limits.limit_for(company.pk, name) == LIMITS[name]

    def test_a_company_override_replaces_the_plans_value(self, company):
        LimitOverride.objects.create(company=company, name="cvs_per_month", value=50)
        assert limits.limit_for(company.pk, "cvs_per_month") == 50
        assert limits.limit_for(company.pk, "max_projects") == LIMITS["max_projects"]

    def test_an_override_applies_to_its_own_company_only(self, company):
        other = make_company()
        LimitOverride.objects.create(company=company, name="cvs_per_month", value=50)
        assert limits.limit_for(other.pk, "cvs_per_month") == 0

    def test_a_change_takes_effect_at_once(self, company):
        score(company, 5)
        assert not limits.check_cvs_this_month(company.pk).allowed
        LimitOverride.objects.create(company=company, name="cvs_per_month", value=6)
        assert limits.check_cvs_this_month(company.pk).allowed
        LimitOverride.objects.filter(company=company).update(value=5)
        assert not limits.check_cvs_this_month(company.pk).allowed

    def test_a_plan_edit_applied_now_takes_effect_at_once(self, company, plan):
        score(company, 5)
        Plan.objects.filter(pk=plan.pk).update(cvs_per_month=8)
        assert limits.check_cvs_this_month(company.pk).room == 3

    def test_a_company_with_no_plan_has_no_allowance_except_the_team_default(self):
        company = make_company()
        assert limits.limit_for(company.pk, "cvs_per_month") == 0
        assert limits.limit_for(company.pk, "max_team_accounts") == get_setting(
            "team.max_accounts_per_company"
        )
        check = limits.check_cvs_this_month(company.pk)
        assert (check.allowed, check.prompt) == (False, "upgrade")

    def test_an_unknown_limit_is_a_mistake(self, company):
        with pytest.raises(KeyError):
            limits.limit_for(company.pk, "nonsense")


class TestEachLimitBlocks:
    def test_cvs_this_month_counts_scored_and_waiting(self, company):
        score(company, 3)
        usage.accept_cv(company.pk, uuid.uuid4())  # waiting
        usage.accept_cv(company.pk, uuid.uuid4())  # waiting
        check = limits.check_cvs_this_month(company.pk)
        assert (check.allowed, check.used, check.room) == (False, 5, 0)
        assert check.code == "monthly_cv_limit_reached"
        assert "5 CVs this month" in check.message
        assert check.prompt == "upgrade"

    def test_one_less_than_the_limit_is_allowed(self, company):
        score(company, 4)
        check = limits.check_cvs_this_month(company.pk)
        assert (check.allowed, check.room) == (True, 1)
        assert not limits.check_cvs_this_month(company.pk, 2).allowed

    def test_a_failed_cv_gives_its_allowance_back(self, company):
        score(company, 3)
        waiting = [uuid.uuid4(), uuid.uuid4()]
        for cv in waiting:
            usage.accept_cv(company.pk, cv)
        assert not limits.check_cvs_this_month(company.pk).allowed
        usage.mark_failed(company.pk, waiting[0])
        assert limits.check_cvs_this_month(company.pk).room == 1

    def test_the_month_restarts_with_the_period(self, company):
        old = uuid.uuid4()
        usage.accept_cv(company.pk, old, now=timezone.now() - 40 * DAY)
        usage.mark_scored(company.pk, old)
        assert limits.check_cvs_this_month(company.pk).used == 0

    def test_cvs_per_project(self, company):
        assert limits.check_cvs_per_project(company.pk, 2).allowed
        check = limits.check_cvs_per_project(company.pk, 3)
        assert (check.allowed, check.code, check.limit) == (False, "project_cv_limit_reached", 3)
        assert "3 CVs" in check.message

    def test_number_of_projects(self, company):
        assert limits.check_projects(company.pk, 1).allowed
        check = limits.check_projects(company.pk, 2)
        assert (check.allowed, check.code) == (False, "project_limit_reached")
        assert "2 projects" in check.message

    def test_top_n_size(self, company):
        assert limits.check_top_n(company.pk, 10).allowed
        check = limits.check_top_n(company.pk, 11)
        assert (check.allowed, check.code, check.limit) == (False, "top_n_limit_exceeded", 10)
        assert "at most 10" in check.message

    def test_team_size(self, company):
        assert limits.check_team_size(company.pk, 1).allowed
        check = limits.check_team_size(company.pk, 2)
        assert (check.allowed, check.code) == (False, "team_limit_reached")
        assert "at most 2 accounts" in check.message

    def test_a_blocked_check_raises_the_shared_error_with_the_prompt(self, company):
        with pytest.raises(AppError) as error:
            limits.check_projects(company.pk, 2).raise_if_blocked()
        assert error.value.code == "project_limit_reached"
        assert error.value.status_code == 409
        assert error.value.details == {"limit": 2, "prompt": "upgrade"}

    def test_an_allowed_check_raises_nothing(self, company):
        limits.check_projects(company.pk, 0).raise_if_blocked()


class TestTheTokenCap:
    def test_ai_is_allowed_below_the_cap(self, company):
        usage.add_tokens(company.pk, 400, 100, "0.1")
        assert limits.check_ai_allowed(company.pk).allowed

    def test_reaching_the_cap_pauses_ai_with_a_clear_message(self, company):
        usage.add_tokens(company.pk, 600, 400, "0.1")  # in and out together
        check = limits.check_ai_allowed(company.pk)
        assert (check.allowed, check.code, check.prompt) == (
            False,
            "ai_paused_token_cap",
            "upgrade",
        )
        assert "paused until the next period" in check.message

    def test_a_limit_increase_resumes_it_at_once(self, company):
        usage.add_tokens(company.pk, 600, 400, "0.1")
        LimitOverride.objects.create(company=company, name="monthly_ai_token_cap", value=2000)
        assert limits.check_ai_allowed(company.pk).allowed

    def test_the_next_period_resumes_it(self, company):
        usage.add_tokens(company.pk, 600, 400, "0.1", now=timezone.now() - 40 * DAY)
        assert limits.check_ai_allowed(company.pk).allowed


class TestWhichPrompt:
    def test_a_lower_plan_gets_upgrade(self, company):
        assert limits.prompt_kind(company.pk) == "upgrade"

    def test_the_highest_plan_gets_renewal(self, top_plan):
        company = make_company()
        subscribe(company, top_plan)
        assert limits.prompt_kind(company.pk) == "renewal"
        assert limits.check_projects(company.pk, 2).prompt == "renewal"

    def test_the_only_plan_is_the_highest(self, plan):
        company = make_company()
        subscribe(company, plan)
        assert limits.prompt_kind(company.pk) == "renewal"

    def test_an_expired_subscription_gets_renewal_for_every_check(self, company):
        subs.expire(company.pk)
        checks = [
            limits.check_cvs_this_month(company.pk),
            limits.check_cvs_per_project(company.pk, 0),
            limits.check_projects(company.pk, 0),
            limits.check_top_n(company.pk, 1),
            limits.check_team_size(company.pk, 0),
            limits.check_ai_allowed(company.pk),
        ]
        assert [c.allowed for c in checks] == [False] * 6
        assert {(c.code, c.prompt) for c in checks} == {("subscription_expired", "renewal")}


class TestPartialBatches:
    def files(self, count):
        return [f"file{i}.pdf" for i in range(count)]

    def test_a_batch_that_fits_is_accepted_whole(self, company):
        split = limits.split_batch(company.pk, self.files(3), cvs_in_project=0)
        assert (len(split.accepted), split.skipped) == (3, [])

    def test_a_larger_batch_accepts_up_to_the_month_limit_and_lists_the_rest(self, company):
        score(company, 3)  # 2 left this month; project has plenty of room
        LimitOverride.objects.create(company=company, name="cvs_per_project", value=100)
        split = limits.split_batch(company.pk, self.files(5), cvs_in_project=3)
        assert split.accepted == ["file0.pdf", "file1.pdf"]
        assert [s.file for s in split.skipped] == ["file2.pdf", "file3.pdf", "file4.pdf"]
        assert {s.code for s in split.skipped} == {"monthly_cv_limit_reached"}
        assert {s.prompt for s in split.skipped} == {"upgrade"}

    def test_the_project_limit_can_be_the_one_that_runs_out(self, company):
        split = limits.split_batch(company.pk, self.files(4), cvs_in_project=1)  # room 2 of 3
        assert split.accepted == ["file0.pdf", "file1.pdf"]
        assert {s.code for s in split.skipped} == {"project_cv_limit_reached"}

    def test_the_tighter_of_the_two_limits_decides(self, company):
        score(company, 4)  # month room 1, project room 2
        split = limits.split_batch(company.pk, self.files(3), cvs_in_project=1)
        assert split.accepted == ["file0.pdf"]
        assert {s.code for s in split.skipped} == {"monthly_cv_limit_reached"}

    def test_waiting_files_use_up_the_room(self, company):
        for _ in range(4):
            usage.accept_cv(company.pk, uuid.uuid4())
        split = limits.split_batch(company.pk, self.files(2), cvs_in_project=0)
        assert len(split.accepted) == 1 and len(split.skipped) == 1

    def test_nothing_left_skips_every_file(self, company):
        score(company, 5)
        split = limits.split_batch(company.pk, self.files(2), cvs_in_project=0)
        assert split.accepted == [] and len(split.skipped) == 2

    def test_an_expired_subscription_skips_every_file_with_renewal(self, company):
        subs.expire(company.pk)
        split = limits.split_batch(company.pk, self.files(2), cvs_in_project=0)
        assert split.accepted == []
        assert {(s.code, s.prompt) for s in split.skipped} == {("subscription_expired", "renewal")}

    def test_an_empty_batch_is_fine(self, company):
        split = limits.split_batch(company.pk, [], cvs_in_project=0)
        assert (split.accepted, split.skipped) == ([], [])

    def test_files_that_failed_later_make_room_for_the_next_batch(self, company):
        cvs = [uuid.uuid4() for _ in range(5)]
        for cv in cvs:
            usage.accept_cv(company.pk, cv)
        assert limits.split_batch(company.pk, ["a"], cvs_in_project=0).accepted == []
        usage.mark_failed(company.pk, cvs[0])
        assert limits.split_batch(company.pk, ["a"], cvs_in_project=0).accepted == ["a"]


class TestTheInviteUsesTheTeamLimit:
    def owner_of(self, company):
        return company.users.get(role="owner")

    def test_the_plans_team_size_stops_an_invite_with_the_prompt(self, company):
        invite_member(self.owner_of(company), "first@example.test")  # owner + 1 = 2 seats
        with pytest.raises(AppError) as error:
            invite_member(self.owner_of(company), "second@example.test")
        assert error.value.code == "team_limit_reached"
        assert error.value.details == {"limit": 2, "prompt": "upgrade"}

    def test_an_admin_override_changes_it_at_once(self, company):
        invite_member(self.owner_of(company), "first@example.test")
        LimitOverride.objects.create(company=company, name="max_team_accounts", value=3)
        invite_member(self.owner_of(company), "second@example.test")

    def test_an_expired_company_cannot_invite_and_is_offered_renewal(self, company):
        subs.expire(company.pk)
        with pytest.raises(AppError) as error:
            invite_member(self.owner_of(company), "first@example.test")
        assert error.value.details["prompt"] == "renewal"
