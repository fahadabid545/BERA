import pytest
from rest_framework.test import APIClient

from core.tests.factories import make_company, make_company_user, start_session_for

pytestmark = pytest.mark.django_db
URL = "/api/auth/company/me/"


def test_it_says_who_is_signed_in_and_nothing_more():
    company = make_company(name="Fake Test Company")
    member = make_company_user(company, name="Fake Member", role="member")
    issued = start_session_for(
        user_id=member.pk, role="member", company_id=company.pk, kind="company"
    )
    response = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}").get(URL)
    assert response.json() == {
        "name": "Fake Member",
        "company_name": "Fake Test Company",
        "role": "member",
    }


def test_it_needs_a_company_sign_in():
    assert APIClient().get(URL).status_code == 401
    admin = start_session_for(user_id=1, role="super", company_id=None, kind="admin")
    assert APIClient(HTTP_AUTHORIZATION=f"Bearer {admin.access_token}").get(URL).status_code == 401
