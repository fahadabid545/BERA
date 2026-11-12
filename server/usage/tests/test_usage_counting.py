import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import connection

from core.tests.factories import make_company
from plans.models import Subscription
from usage import service
from usage.models import CvUsage, UsageCounter, UsagePeriod

pytestmark = pytest.mark.django_db


def at(year, month, day, hour=0):
    return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.fixture
def company():
    company = make_company()
    Subscription.objects.create(company=company, period_start=at(2030, 1, 15), state="active")
    return company


def counters(company, project=None):
    return UsageCounter.objects.filter(company=company, project_id=project)


def scored_total(company):
    return sum(c.cvs_scored for c in UsageCounter.objects.filter(company=company))


class TestThePeriod:
    def test_a_period_runs_from_the_subscription_start_day_each_month(self, company):
        assert service.window_for(company.pk, at(2030, 1, 20)) == (at(2030, 1, 15), at(2030, 2, 15))
        assert service.window_for(company.pk, at(2030, 2, 14, 23)) == (
            at(2030, 1, 15),
            at(2030, 2, 15),
        )
        assert service.window_for(company.pk, at(2030, 2, 15)) == (at(2030, 2, 15), at(2030, 3, 15))

    def test_a_year_boundary_works(self, company):
        assert service.window_for(company.pk, at(2030, 12, 31)) == (
            at(2030, 12, 15),
            at(2031, 1, 15),
        )

    def test_a_start_on_the_31st_uses_the_last_day_of_short_months(self, company):
        Subscription.objects.filter(company=company).update(period_start=at(2030, 1, 31))
        assert service.window_for(company.pk, at(2030, 2, 10)) == (at(2030, 1, 31), at(2030, 2, 28))
        assert service.window_for(company.pk, at(2030, 3, 5)) == (at(2030, 2, 28), at(2030, 3, 31))

    def test_a_moment_before_the_start_still_has_a_period(self, company):
        assert service.window_for(company.pk, at(2029, 12, 20)) == (
            at(2029, 12, 15),
            at(2030, 1, 15),
        )

    def test_a_company_with_no_subscription_start_follows_its_sign_up_day(self):
        company = make_company()
        start, end = service.window_for(company.pk, company.created_at)
        assert start <= company.created_at < end


class TestCountingCvs:
    def test_a_cv_counts_once_when_it_is_scored(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        assert scored_total(company) == 0
        assert service.mark_scored(company.pk, cv) is True
        assert scored_total(company) == 1

    def test_rescoring_never_counts_again(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        service.mark_scored(company.pk, cv)
        assert service.mark_scored(company.pk, cv) is False
        assert scored_total(company) == 1

    def test_a_failed_cv_is_never_counted_and_stops_waiting(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        assert service.waiting_cvs(company.pk) == 1
        assert service.mark_failed(company.pk, cv) is True
        assert service.waiting_cvs(company.pk) == 0
        assert scored_total(company) == 0

    def test_a_counted_cv_stays_counted_if_a_later_run_fails(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        service.mark_scored(company.pk, cv)
        assert service.mark_failed(company.pk, cv) is False
        assert scored_total(company) == 1

    def test_accepting_the_same_cv_twice_is_one_cv(self, company):
        cv = uuid.uuid4()
        first = service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        second = service.accept_cv(company.pk, cv, now=at(2030, 3, 1))
        assert first.pk == second.pk
        assert CvUsage.objects.filter(company=company).count() == 1

    def test_scoring_a_cv_that_was_never_accepted_is_a_mistake(self, company):
        with pytest.raises(CvUsage.DoesNotExist):
            service.mark_scored(company.pk, uuid.uuid4())

    def test_a_cv_of_another_company_cannot_be_counted_through_this_one(self, company):
        other = make_company()
        cv = uuid.uuid4()
        service.accept_cv(other.pk, cv, now=at(2030, 1, 20))
        with pytest.raises(CvUsage.DoesNotExist):
            service.mark_scored(company.pk, cv)
        assert scored_total(other) == 0 and scored_total(company) == 0


class TestTokens:
    def test_tokens_and_cost_add_up(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        service.add_tokens(company.pk, 100, 20, "0.010000", cv_id=cv)
        service.add_tokens(company.pk, 50, 5, "0.002500", cv_id=cv)
        usage = service.current_usage(company.pk, at(2030, 1, 25))
        assert (usage["tokens_in"], usage["tokens_out"]) == (150, 25)
        assert usage["estimated_cost"] == Decimal("0.012500")

    def test_rescoring_tokens_count_but_not_the_cv(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        service.add_tokens(company.pk, 100, 10, "0.01", cv_id=cv)
        service.mark_scored(company.pk, cv)
        service.add_tokens(company.pk, 100, 10, "0.01", cv_id=cv)
        service.mark_scored(company.pk, cv)
        usage = service.current_usage(company.pk, at(2030, 1, 25))
        assert (usage["cvs_scored"], usage["tokens_in"]) == (1, 200)

    def test_work_with_no_cv_counts_in_the_period_of_now(self, company):
        service.add_tokens(company.pk, 7, 3, "0.001", now=at(2030, 2, 20))
        assert service.current_usage(company.pk, at(2030, 2, 21))["tokens_in"] == 7
        assert service.current_usage(company.pk, at(2030, 1, 21))["tokens_in"] == 0

    @pytest.mark.parametrize("bad", [(-1, 0, "0"), (0, -1, "0"), (0, 0, "-0.1")])
    def test_negative_usage_is_refused(self, company, bad):
        with pytest.raises(ValueError):
            service.add_tokens(company.pk, bad[0], bad[1], bad[2])


class TestPeriodChanges:
    def test_a_cv_scored_after_the_period_ended_counts_where_it_was_accepted(self, company):
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 2, 14, 23))
        service.add_tokens(company.pk, 100, 10, "0.01", cv_id=cv, now=at(2030, 2, 15, 1))
        service.mark_scored(company.pk, cv)  # scored in the next period
        january = service.current_usage(company.pk, at(2030, 2, 14, 23))
        february = service.current_usage(company.pk, at(2030, 2, 16))
        assert (january["cvs_scored"], january["tokens_in"]) == (1, 100)
        assert (february["cvs_scored"], february["tokens_in"]) == (0, 0)

    def test_counters_restart_in_the_new_period_and_history_is_kept(self, company):
        first, second = uuid.uuid4(), uuid.uuid4()
        service.accept_cv(company.pk, first, now=at(2030, 1, 20))
        service.mark_scored(company.pk, first)
        service.accept_cv(company.pk, second, now=at(2030, 2, 20))
        service.mark_scored(company.pk, second)
        history = service.usage_history(company.pk)
        assert [(h["period_start"], h["cvs_scored"]) for h in history] == [
            (at(2030, 2, 15), 1),
            (at(2030, 1, 15), 1),
        ]
        assert service.current_usage(company.pk, at(2030, 2, 25))["cvs_scored"] == 1

    def test_a_new_start_day_after_renewal_never_overlaps_the_period_before(self, company):
        service.accept_cv(company.pk, uuid.uuid4(), now=at(2030, 1, 20))  # period 15 Jan - 15 Feb
        Subscription.objects.filter(company=company).update(period_start=at(2030, 2, 10))
        service.accept_cv(company.pk, uuid.uuid4(), now=at(2030, 2, 16))
        periods = list(UsagePeriod.objects.filter(company=company).order_by("start"))
        assert len(periods) == 2
        assert periods[0].end <= periods[1].start
        assert periods[1].start <= at(2030, 2, 16) < periods[1].end

    def test_reading_usage_creates_nothing(self, company):
        service.current_usage(company.pk, at(2030, 5, 5))
        assert UsagePeriod.objects.count() == 0


class TestPerProject:
    def test_counts_are_kept_per_project_and_sum_to_the_company(self, company):
        a, b = uuid.uuid4(), uuid.uuid4()
        for project, cvs in ((a, 2), (b, 1)):
            for _ in range(cvs):
                cv = uuid.uuid4()
                service.accept_cv(company.pk, cv, project, now=at(2030, 1, 20))
                service.add_tokens(company.pk, 10, 1, "0.001", cv_id=cv)
                service.mark_scored(company.pk, cv)
        usage = service.current_usage(company.pk, at(2030, 1, 21))
        assert usage["cvs_scored"] == 3 and usage["tokens_in"] == 30
        assert usage["projects"][str(a)]["cvs_scored"] == 2
        assert usage["projects"][str(b)]["cvs_scored"] == 1

    def test_companies_are_kept_apart(self, company):
        other = make_company()
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        service.mark_scored(company.pk, cv)
        assert service.usage_history(other.pk) == []
        assert service.current_usage(other.pk)["cvs_scored"] == 0


class TestOnlyTheServerCanChangeCounters:
    def test_no_route_reaches_the_counters(self):
        from core.tests.test_route_protection import all_routes

        assert not [r for r, _ in all_routes() if "usage" in r]


@pytest.mark.django_db(transaction=True)
class TestParallelWork:
    def run_in_parallel(self, work, jobs):
        def run(job):
            try:
                return work(job)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(run, jobs))

    def make_company(self):
        company = make_company()
        Subscription.objects.create(company=company, period_start=at(2030, 1, 15), state="active")
        return company

    def test_one_cv_scored_by_many_workers_at_once_counts_once(self):
        company = self.make_company()
        cv = uuid.uuid4()
        service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
        results = self.run_in_parallel(lambda _: service.mark_scored(company.pk, cv), range(16))
        assert results.count(True) == 1
        assert scored_total(company) == 1

    def test_many_uploads_at_once_are_each_counted_exactly_once(self):
        company = self.make_company()
        cvs = [uuid.uuid4() for _ in range(24)]

        def upload(cv):
            service.accept_cv(company.pk, cv, now=at(2030, 1, 20))
            service.add_tokens(company.pk, 10, 2, "0.001", cv_id=cv)
            service.mark_scored(company.pk, cv)

        self.run_in_parallel(upload, cvs)
        usage = service.current_usage(company.pk, at(2030, 1, 21))
        assert usage["cvs_scored"] == 24
        assert (usage["tokens_in"], usage["tokens_out"]) == (240, 48)
        assert usage["estimated_cost"] == Decimal("0.024")
        assert UsagePeriod.objects.filter(company=company).count() == 1

    def test_the_same_cv_accepted_by_many_workers_is_one_entry(self):
        company = self.make_company()
        cv = uuid.uuid4()
        self.run_in_parallel(
            lambda _: service.accept_cv(company.pk, cv, now=at(2030, 1, 20)), range(12)
        )
        assert CvUsage.objects.filter(company=company).count() == 1

    def test_uploads_across_a_period_change_land_in_the_right_periods(self):
        company = self.make_company()
        before = [(uuid.uuid4(), at(2030, 2, 14, 23)) for _ in range(6)]
        after = [(uuid.uuid4(), at(2030, 2, 15, 1)) for _ in range(6)]

        def upload(item):
            cv, moment = item
            service.accept_cv(company.pk, cv, now=moment)
            service.mark_scored(company.pk, cv)

        self.run_in_parallel(upload, before + after)
        assert service.current_usage(company.pk, at(2030, 2, 14, 23))["cvs_scored"] == 6
        assert service.current_usage(company.pk, at(2030, 2, 16))["cvs_scored"] == 6
        assert UsagePeriod.objects.filter(company=company).count() == 2
