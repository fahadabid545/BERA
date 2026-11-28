import pytest
from django.utils import timezone

from core.tests.factories import make_company
from plans import subscriptions as subs
from plans.models import Plan
from projects.models import Project

from .helpers import LONG_TEXT, sign_in


@pytest.fixture
def company():
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
    )
    subs.activate(company.pk, plan, period_start=now, period_end=now + timezone.timedelta(days=30))
    return company


@pytest.fixture
def signed_in(company):
    return sign_in(company)


@pytest.fixture
def project(company, signed_in):
    person, _ = signed_in
    return Project.objects.create(
        company=company,
        title="Backend engineer",
        job_description=LONG_TEXT,
        reading_model="pinned-model",
        created_by=person,
    )


@pytest.fixture
def owner(signed_in):
    return signed_in[1]
