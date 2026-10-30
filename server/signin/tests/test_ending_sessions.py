from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated
from rest_framework.test import APIClient

from companies.models import CompanyUser
from core.tests.factories import make_admin_user, make_company, make_company_user
from signin import service
from signin.cookies import CSRF_COOKIE, access_cookie_name, refresh_cookie_name
from signin.models import Session
from signin.service import RevokeReason

LOGOUT = "/api/auth/{kind}/logout/"
LOGOUT_ALL = "/api/auth/{kind}/logout-all/"
REFRESH = "/api/auth/{kind}/refresh/"
CSRF = "csrf-value"

pytestmark = pytest.mark.django_db


def sign_in(person=None, kind="company"):
    if kind == "admin":
        person = person or make_admin_user()
        return person, service.start_session(
            user_id=person.pk, role="super", company_id=None, kind="admin"
        )
    person = person or make_company_user(role="member")
    return person, service.start_session(
        user_id=person.pk, role="member", company_id=person.company_id, kind="company"
    )


def browser_of(issued, kind="company", csrf=CSRF):
    client = APIClient(REMOTE_ADDR="203.0.113.5")
    client.cookies[access_cookie_name(kind)] = issued.access_token
    client.cookies[refresh_cookie_name(kind)] = issued.refresh_token
    client.cookies[CSRF_COOKIE] = csrf
    return client


def post(client, template, kind="company", csrf=CSRF):
    return client.post(template.format(kind=kind), HTTP_X_CSRF_TOKEN=csrf)


def refused(issued, kind="company"):
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.access_token, kind)


def cleared(response, kind="company"):
    names = [access_cookie_name(kind), refresh_cookie_name(kind), CSRF_COOKIE]
    return all(response.cookies[name]["max-age"] == 0 for name in names)


@pytest.mark.parametrize("kind", ["company", "admin"])
class TestLoggingOut:
    def test_it_ends_the_current_session_and_clears_the_cookies(self, kind):
        _, issued = sign_in(kind=kind)
        response = post(browser_of(issued, kind), LOGOUT, kind)
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        assert cleared(response, kind)
        session = Session.objects.get()
        assert (session.status, session.revoke_reason) == ("revoked", RevokeReason.LOGOUT)

    def test_the_tokens_are_refused_at_once_even_though_they_have_not_expired(self, kind):
        _, issued = sign_in(kind=kind)
        post(browser_of(issued, kind), LOGOUT, kind)
        refused(issued, kind)
        renewed = APIClient(REMOTE_ADDR="203.0.113.5")
        renewed.cookies[refresh_cookie_name(kind)] = issued.refresh_token
        renewed.cookies[CSRF_COOKIE] = CSRF
        assert post(renewed, REFRESH, kind).status_code == 401

    def test_other_devices_stay_signed_in(self, kind):
        person, first = sign_in(kind=kind)
        _, second = sign_in(person, kind)
        post(browser_of(first, kind), LOGOUT, kind)
        refused(first, kind)
        assert service.verify_access_token(second.access_token, kind)

    def test_it_works_after_the_access_token_has_ended(self, kind):
        _, issued = sign_in(kind=kind)
        client = browser_of(issued, kind)
        del client.cookies[access_cookie_name(kind)]
        assert post(client, LOGOUT, kind).status_code == 200
        assert Session.objects.get().status == "revoked"

    def test_signing_out_twice_or_with_nothing_is_harmless(self, kind):
        _, issued = sign_in(kind=kind)
        client = browser_of(issued, kind)
        assert post(client, LOGOUT, kind).status_code == 200
        assert post(client, LOGOUT, kind).status_code == 200
        nobody = APIClient(REMOTE_ADDR="203.0.113.5")
        response = post(nobody, LOGOUT, kind)
        assert response.status_code == 200 and cleared(response, kind)

    def test_a_made_up_refresh_cookie_ends_nothing_and_still_clears(self, kind):
        _, issued = sign_in(kind=kind)
        client = APIClient(REMOTE_ADDR="203.0.113.5")
        client.cookies[refresh_cookie_name(kind)] = "not-a-token"
        client.cookies[CSRF_COOKIE] = CSRF
        response = post(client, LOGOUT, kind)
        assert response.status_code == 200 and cleared(response, kind)
        assert Session.objects.get().status == "active"

    def test_another_site_cannot_sign_a_person_out(self, kind):
        _, issued = sign_in(kind=kind)
        client = browser_of(issued, kind)
        assert post(client, LOGOUT, kind, csrf="something-else").status_code == 403
        assert Session.objects.get().status == "active"

    def test_the_other_kind_of_sign_in_is_not_ended(self, kind):
        other = "admin" if kind == "company" else "company"
        _, issued = sign_in(kind=kind)
        _, other_issued = sign_in(kind=other)
        client = browser_of(issued, kind)
        client.cookies[refresh_cookie_name(kind)] = other_issued.refresh_token  # wrong kind
        post(client, LOGOUT, kind)
        assert service.verify_access_token(other_issued.access_token, other)


@pytest.mark.parametrize("kind", ["company", "admin"])
class TestSigningOutOfAllDevices:
    def test_it_ends_every_session_of_that_person(self, kind):
        person, first = sign_in(kind=kind)
        _, second = sign_in(person, kind)
        _, third = sign_in(person, kind)
        response = post(browser_of(first, kind), LOGOUT_ALL, kind)
        assert response.status_code == 200 and cleared(response, kind)
        for issued in (first, second, third):
            refused(issued, kind)
        assert set(Session.objects.values_list("revoke_reason", flat=True)) == {
            RevokeReason.LOGOUT_ALL
        }

    def test_other_people_are_not_affected(self, kind):
        person, mine = sign_in(kind=kind)
        _, theirs = sign_in(kind=kind)
        post(browser_of(mine, kind), LOGOUT_ALL, kind)
        assert service.verify_access_token(theirs.access_token, kind)

    def test_the_same_token_cannot_be_used_again(self, kind):
        _, issued = sign_in(kind=kind)
        client = browser_of(issued, kind)
        post(client, LOGOUT_ALL, kind)
        client.cookies[access_cookie_name(kind)] = issued.access_token
        assert post(client, LOGOUT_ALL, kind).status_code == 401

    def test_it_needs_a_signed_in_person(self, kind):
        assert post(APIClient(REMOTE_ADDR="203.0.113.5"), LOGOUT_ALL, kind).status_code == 401

    def test_another_site_cannot_do_it(self, kind):
        _, issued = sign_in(kind=kind)
        client = browser_of(issued, kind)
        assert post(client, LOGOUT_ALL, kind, csrf="something-else").status_code == 403
        assert Session.objects.get().status == "active"


def test_signing_out_everywhere_leaves_the_other_kind_of_sign_in_alone():
    _, company_session = sign_in()
    _, admin_session = sign_in(kind="admin")
    post(browser_of(company_session), LOGOUT_ALL)
    assert service.verify_access_token(admin_session.access_token, "admin")


class TestWhenTheRefreshTokenRunsOut:
    def test_the_session_cannot_be_renewed_or_used_after_it_expires(self):
        _, issued = sign_in()
        Session.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        refused(issued)
        client = APIClient(REMOTE_ADDR="203.0.113.5")
        client.cookies[refresh_cookie_name("company")] = issued.refresh_token
        client.cookies[CSRF_COOKIE] = CSRF
        assert post(client, REFRESH).status_code == 401


class TestBlockedAndRemovedPeople:
    @pytest.mark.parametrize(("status", "reason"), [("blocked", "blocked"), ("removed", "removed")])
    def test_their_sessions_end_when_they_are_blocked_or_removed(self, status, reason):
        company = make_company()
        make_company_user(company, role="owner")
        person = make_company_user(company, role="member")
        _, first = sign_in(person)
        _, second = sign_in(person)
        person.status = status
        person.save()
        refused(first), refused(second)
        assert set(Session.objects.values_list("status", "revoke_reason")) == {("revoked", reason)}

    def test_being_active_again_does_not_bring_old_sessions_back(self):
        person, issued = sign_in()
        person.status = "blocked"
        person.save()
        person.status = "active"
        person.save()
        refused(issued)

    def test_a_blocked_admin_loses_their_sessions_too(self):
        admin, issued = sign_in(kind="admin")
        admin.status = "blocked"
        admin.save()
        refused(issued, "admin")

    def test_only_that_person_is_affected(self):
        person, mine = sign_in()
        _, theirs = sign_in()
        person.status = "blocked"
        person.save()
        assert service.verify_access_token(theirs.access_token, "company")

    def test_a_bulk_update_is_still_refused_at_once(self):
        person, issued = sign_in()
        CompanyUser.objects.filter(pk=person.pk).update(status="blocked")
        refused(issued)


class TestChangingThePassword:
    def test_it_ends_every_session_of_that_person(self):
        person, first = sign_in()
        _, second = sign_in(person)
        person.set_password("another-long-fake-password-9")
        person.save()
        refused(first), refused(second)
        assert set(Session.objects.values_list("revoke_reason", flat=True)) == {
            RevokeReason.PASSWORD_CHANGED
        }

    def test_a_new_session_started_afterwards_works(self):
        person, _ = sign_in()
        person.set_password("another-long-fake-password-9")
        person.save()
        _, fresh = sign_in(person)
        assert service.verify_access_token(fresh.access_token, "company")

    def test_saving_without_a_new_password_ends_nothing(self):
        person, issued = sign_in()
        person = CompanyUser.objects.get(pk=person.pk)
        person.name = "A New Fake Name"
        person.save()
        assert service.verify_access_token(issued.access_token, "company")

    def test_other_people_keep_their_sessions(self):
        person, _ = sign_in()
        _, theirs = sign_in()
        person.set_password("another-long-fake-password-9")
        person.save()
        assert service.verify_access_token(theirs.access_token, "company")

    def test_an_admin_changing_their_password_ends_their_sessions(self):
        admin, issued = sign_in(kind="admin")
        admin.set_password("another-long-fake-password-9")
        admin.save()
        refused(issued, "admin")

    def test_creating_a_person_ends_nothing(self):
        _, issued = sign_in()
        make_company_user()
        assert service.verify_access_token(issued.access_token, "company")
