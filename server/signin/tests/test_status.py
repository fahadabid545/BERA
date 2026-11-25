import pytest
from rest_framework.test import APIClient

from companies.models import Company, CompanyUser
from core.tests.factories import make_company, make_company_user, start_session_for
from signin import service
from signin.cookies import access_cookie_name, refresh_cookie_name
from signin.models import Session

pytestmark = pytest.mark.django_db
URL = "/api/auth/company/status/"
SIGNED_OUT = {"signed_in": False, "can_pay": False}


def sign_in(role="owner"):
    company = make_company()
    person = make_company_user(company, role=role)
    issued = start_session_for(user_id=person.pk, role=role, company_id=company.pk, kind="company")
    return person, company, issued


def client_with(*, access=None, refresh=None, kind="company"):
    client = APIClient()
    if access:
        client.cookies[access_cookie_name(kind)] = access
    if refresh:
        client.cookies[refresh_cookie_name(kind)] = refresh
    return client


class TestTheAnswer:
    def test_an_owner_is_signed_in_and_can_pay(self):
        _, _, issued = sign_in("owner")
        reply = client_with(access=issued.access_token).get(URL)
        assert (reply.status_code, reply.json()) == (200, {"signed_in": True, "can_pay": True})

    def test_a_member_is_signed_in_but_cannot_pay(self):
        _, _, issued = sign_in("member")
        reply = client_with(access=issued.access_token).get(URL)
        assert reply.json() == {"signed_in": True, "can_pay": False}

    def test_a_visitor_gets_two_falses_not_a_redirect(self):
        reply = APIClient().get(URL)
        assert (reply.status_code, reply.json()) == (200, SIGNED_OUT)
        assert "Location" not in reply

    def test_nothing_but_the_two_answers_is_ever_returned(self):
        person, company, issued = sign_in("owner")
        body = client_with(access=issued.access_token).get(URL).content.decode()
        assert set(client_with(access=issued.access_token).get(URL).json()) == {
            "signed_in",
            "can_pay",
        }
        assert person.name not in body and company.name not in body

    def test_it_is_never_stored_by_a_cache(self):
        assert APIClient().get(URL)["Cache-Control"] == "no-store"

    def test_it_only_reads(self):
        _, _, issued = sign_in()
        client = client_with(access=issued.access_token)
        assert client.post(URL).status_code == 405
        assert client.delete(URL).status_code == 405

    def test_a_forged_or_wrong_kind_of_sign_in_is_the_same_answer_as_none(self):
        admin = start_session_for(user_id=1, role="super", company_id=None, kind="admin")
        for client in (
            client_with(access="not-a-token", refresh="not-a-token"),
            client_with(access=admin.access_token),
            client_with(access=admin.access_token, kind="admin"),
        ):
            reply = client.get(URL)
            assert (reply.status_code, reply.json()) == (200, SIGNED_OUT)

    def test_a_bearer_header_is_not_a_page_sign_in(self):
        _, _, issued = sign_in()
        reply = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}").get(URL)
        assert reply.json() == SIGNED_OUT

    def test_an_unknown_account_and_a_wrong_one_look_the_same(self):
        first = client_with(access="a.b.c").get(URL)
        second = APIClient().get(URL)
        assert (first.status_code, first.content) == (second.status_code, second.content)


class TestTheSessionRules:
    def test_an_ended_access_token_is_renewed_once_silently(self):
        _, _, issued = sign_in()
        reply = client_with(refresh=issued.refresh_token).get(URL)  # the access cookie expired
        assert reply.json() == {"signed_in": True, "can_pay": True}
        new_access = reply.cookies[access_cookie_name("company")]
        new_refresh = reply.cookies[refresh_cookie_name("company")]
        assert new_refresh.value != issued.refresh_token
        assert new_access["httponly"] is True and new_access["samesite"] == "Strict"
        assert new_refresh["path"] == "/api/auth/company/"

    def test_the_renewed_sign_in_works_and_the_old_refresh_token_does_not(self):
        _, _, issued = sign_in()
        reply = client_with(refresh=issued.refresh_token).get(URL)
        renewed = reply.cookies[access_cookie_name("company")].value
        assert client_with(access=renewed).get(URL).json()["signed_in"] is True
        assert client_with(refresh=issued.refresh_token).get(URL).json() == SIGNED_OUT

    def test_a_valid_access_token_does_not_renew_anything(self):
        _, _, issued = sign_in()
        reply = client_with(access=issued.access_token, refresh=issued.refresh_token).get(URL)
        assert reply.json()["signed_in"] is True
        assert access_cookie_name("company") not in reply.cookies

    def test_an_ended_refresh_token_answers_false_and_sets_nothing(self):
        _, _, issued = sign_in()
        Session.objects.update(status=Session.Status.REVOKED)
        reply = client_with(refresh=issued.refresh_token).get(URL)
        assert reply.json() == SIGNED_OUT
        assert access_cookie_name("company") not in reply.cookies

    def test_a_signed_out_session_answers_false_even_with_both_cookies(self):
        _, _, issued = sign_in()
        service.end_session_of_refresh_token(issued.refresh_token, "company")
        reply = client_with(access=issued.access_token, refresh=issued.refresh_token).get(URL)
        assert reply.json() == SIGNED_OUT

    def test_a_blocked_user_answers_false_and_is_not_renewed(self):
        person, _, issued = sign_in()
        CompanyUser.objects.filter(pk=person.pk).update(status=CompanyUser.Status.BLOCKED)
        assert client_with(access=issued.access_token).get(URL).json() == SIGNED_OUT
        reply = client_with(refresh=issued.refresh_token).get(URL)
        assert reply.json() == SIGNED_OUT and refresh_cookie_name("company") not in reply.cookies

    @pytest.mark.parametrize("state", ["suspended", "pending_deletion"])
    def test_a_company_that_cannot_sign_in_answers_false(self, state):
        _, company, issued = sign_in()
        Company.objects.filter(pk=company.pk).update(status=state)
        assert client_with(access=issued.access_token).get(URL).json() == SIGNED_OUT
        assert client_with(refresh=issued.refresh_token).get(URL).json() == SIGNED_OUT

    def test_a_role_change_applies_at_once(self):
        person, _, issued = sign_in("owner")
        CompanyUser.objects.filter(pk=person.pk).update(role="member")
        reply = client_with(access=issued.access_token).get(URL)
        assert reply.json() == {"signed_in": True, "can_pay": False}

    def test_it_counts_against_the_general_rate_limit(self):
        from core.throttles import OtherRequestsThrottle
        from signin.views import company_status

        assert OtherRequestsThrottle in company_status.cls.throttle_classes
