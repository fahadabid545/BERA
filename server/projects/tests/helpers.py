from rest_framework.test import APIClient

from core.tests.factories import make_company_user, start_session_for

LONG_TEXT = "We need a senior backend engineer who knows Python well. " * 8


def sign_in(company, role="owner"):
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
