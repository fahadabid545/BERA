"""The screens that look again every few seconds have their own allowance, so many open tabs
neither use up the general one nor get refused by it."""

import pytest

from cvs.tests.test_processing import Tenant, make_plan, set_setting
from cvs.tests.test_ranked_list import add

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    tenant = Tenant(make_plan())
    add(tenant, "anna.pdf", 90)
    return tenant


def live_links(tenant):
    project = f"/api/company/projects/{tenant.project.pk}/"
    return [f"{project}candidates/", f"{project}matrix/", f"{project}processing/"]


def test_the_live_screens_answer_with_the_delay_the_page_waits(tenant):
    set_setting("live_updates.max_delay_seconds", 5)
    for link in live_links(tenant):
        assert tenant.client.get(link).json()["refresh_seconds"] == 5


def test_many_open_tabs_do_not_use_up_the_general_allowance(tenant):
    set_setting("rate_limits.other_requests_per_minute", 5)
    for _ in range(40):  # about 13 tabs asking three times a minute each, and more
        for link in live_links(tenant):
            assert tenant.client.get(link).status_code == 200
    # The general allowance is still whole for everything else.
    assert tenant.client.get(f"/api/company/projects/{tenant.project.pk}/cvs/").status_code == 200


def test_the_live_allowance_is_its_own_and_comes_from_a_setting(tenant):
    set_setting("rate_limits.live_updates_per_minute", 4)
    link = live_links(tenant)[0]
    assert [tenant.client.get(link).status_code for _ in range(5)] == [200] * 4 + [429]
    refused = tenant.client.get(link)
    assert refused.json()["error"]["code"] == "too_many_requests"
    assert int(refused["Retry-After"]) > 0


def test_the_live_allowance_is_per_person(tenant):
    set_setting("rate_limits.live_updates_per_minute", 2)
    link = live_links(tenant)[0]
    for _ in range(3):
        tenant.client.get(link)
    other = Tenant(make_plan())
    assert (
        other.client.get(f"/api/company/projects/{other.project.pk}/candidates/").status_code == 200
    )


def test_the_usage_summary_is_live_too(tenant):
    set_setting("rate_limits.other_requests_per_minute", 2)
    answers = {tenant.client.get("/api/company/usage/").status_code for _ in range(6)}
    assert 429 not in answers
