"""Shared set-up for the API key tests: a company with a paid plan, an owner, a project, and a
way to make a key and call the API with it."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from apikeys import service
from apikeys.scopes import SCOPES
from cvs.tests.test_processing import Tenant, make_plan

API = "/api/v1/"
KEYS = "/api/company/api-keys/"


def make_tenant():
    return Tenant(make_plan())


def make_key(tenant, scopes=SCOPES, *, name="Fake key", expires_at=None):
    """(stored key, key text)."""
    return service.create_key(tenant.owner, name, list(scopes), expires_at)


def client_with(token):
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {token}")


def api_client(tenant, scopes=SCOPES):
    _, token = make_key(tenant, scopes)
    return client_with(token)


def end_subscription(company):
    from plans.models import Subscription

    Subscription.objects.filter(company_id=company.pk).update(
        state="expired", period_end=timezone.now() - timedelta(days=1)
    )
