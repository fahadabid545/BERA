from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated

from signin import service
from signin.models import Session
from signin.service import RevokeReason

pytestmark = pytest.mark.django_db


def sign_in(user_id=7, role="owner", company_id=3, kind="company"):
    return service.start_session(user_id=user_id, role=role, company_id=company_id, kind=kind)


def test_a_new_sign_in_can_be_verified():
    issued = sign_in()
    user = service.verify_access_token(issued.access_token, "company")
    assert (user.user_id, user.role, user.company_id, user.kind) == (7, "owner", 3, "company")
    assert user.session_id == issued.session_id


def test_admin_sign_ins_have_no_company():
    issued = sign_in(role="super", company_id=None, kind="admin")
    assert service.verify_access_token(issued.access_token, "admin").company_id is None


@pytest.mark.parametrize(
    ("kind", "role", "company_id"),
    [
        ("company", "super", 3),
        ("admin", "owner", None),
        ("company", "owner", None),
        ("admin", "super", 3),
        ("other", "owner", 3),
    ],
)
def test_issuing_refuses_a_mismatched_kind_role_or_company(kind, role, company_id):
    with pytest.raises(ValueError):
        sign_in(kind=kind, role=role, company_id=company_id)
    assert Session.objects.count() == 0


def test_lifetimes_come_from_platform_settings():
    issued = sign_in()
    assert issued.access_seconds == 15 * 60
    assert issued.refresh_seconds == 7 * 24 * 60 * 60
    session = Session.objects.get()
    assert abs(session.expires_at - (timezone.now() + timedelta(days=7))) < timedelta(minutes=1)


def test_only_a_hash_of_the_refresh_token_is_stored():
    issued = sign_in()
    stored = Session.objects.get().refresh_token_hash
    assert stored != issued.refresh_token and len(stored) == 64


def test_a_company_access_token_does_not_verify_as_admin():
    issued = sign_in()
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.access_token, "admin")


def test_verifying_uses_one_database_lookup(django_assert_num_queries):
    issued = sign_in()
    with django_assert_num_queries(1):
        service.verify_access_token(issued.access_token, "company")


def test_a_refresh_token_cannot_be_used_as_an_access_token():
    issued = sign_in()
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.refresh_token, "company")


def test_refreshing_gives_new_tokens_and_the_old_refresh_token_stops_working():
    first = sign_in()
    second = service.refresh_session(first.refresh_token, "company")

    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token
    service.verify_access_token(second.access_token, "company")
    # The next refresh with the new token works too.
    service.refresh_session(second.refresh_token, "company")


def test_reusing_a_used_refresh_token_ends_the_whole_session():
    first = sign_in()
    second = service.refresh_session(first.refresh_token, "company")

    with pytest.raises(NotAuthenticated):
        service.refresh_session(first.refresh_token, "company")  # a copy being replayed

    session = Session.objects.get()
    assert session.status == Session.Status.REVOKED
    assert session.revoke_reason == RevokeReason.REFRESH_REUSE
    # The thief's new tokens and the real user's are all dead.
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(second.access_token, "company")
    with pytest.raises(NotAuthenticated):
        service.refresh_session(second.refresh_token, "company")


def test_an_old_token_from_several_refreshes_ago_also_counts_as_reuse():
    first = sign_in()
    second = service.refresh_session(first.refresh_token, "company")
    service.refresh_session(second.refresh_token, "company")
    with pytest.raises(NotAuthenticated):
        service.refresh_session(first.refresh_token, "company")
    assert Session.objects.get().status == Session.Status.REVOKED


def test_refreshing_with_the_wrong_kind_fails_without_ending_the_session():
    issued = sign_in()
    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.refresh_token, "admin")
    assert Session.objects.get().status == Session.Status.ACTIVE


def test_an_access_token_cannot_be_used_to_refresh():
    issued = sign_in()
    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.access_token, "company")


def test_an_expired_session_cannot_be_used_or_refreshed():
    issued = sign_in()
    Session.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.access_token, "company")
    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.refresh_token, "company")


@pytest.mark.parametrize(
    "reason",
    [
        RevokeReason.LOGOUT,
        RevokeReason.PASSWORD_CHANGED,
        RevokeReason.ROLE_CHANGED,
        RevokeReason.BLOCKED,
        RevokeReason.COMPANY_SUSPENDED,
    ],
)
def test_revoking_a_session_ends_its_tokens_at_once(reason):
    issued = sign_in()
    assert service.revoke_session(issued.session_id, reason) == 1

    with pytest.raises(NotAuthenticated):
        service.verify_access_token(issued.access_token, "company")  # not yet expired
    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.refresh_token, "company")
    assert Session.objects.get().revoke_reason == reason


def test_revoking_one_session_leaves_the_others():
    mine = sign_in()
    other_device = sign_in()
    service.revoke_session(mine.session_id, RevokeReason.LOGOUT)
    service.verify_access_token(other_device.access_token, "company")


def test_revoking_all_sessions_of_a_user_across_kinds_or_one_kind():
    laptop, phone = sign_in(user_id=7), sign_in(user_id=7)
    someone_else = sign_in(user_id=8)
    admin_session = sign_in(user_id=7, role="super", company_id=None, kind="admin")

    assert service.revoke_user_sessions(7, RevokeReason.BLOCKED, kind="company") == 2
    service.verify_access_token(admin_session.access_token, "admin")
    assert service.revoke_user_sessions(7, RevokeReason.BLOCKED) == 1

    for issued in (laptop, phone):
        with pytest.raises(NotAuthenticated):
            service.verify_access_token(issued.access_token, "company")
    service.verify_access_token(someone_else.access_token, "company")


def test_revoking_all_sessions_of_a_company():
    owner, member = (
        sign_in(user_id=1, company_id=3),
        sign_in(user_id=2, role="member", company_id=3),
    )
    other_company = sign_in(user_id=3, company_id=4)
    admin_session = sign_in(user_id=1, role="super", company_id=None, kind="admin")

    assert service.revoke_company_sessions(3, RevokeReason.COMPANY_SUSPENDED) == 2

    for issued in (owner, member):
        with pytest.raises(NotAuthenticated):
            service.verify_access_token(issued.access_token, "company")
    service.verify_access_token(other_company.access_token, "company")
    service.verify_access_token(admin_session.access_token, "admin")


def test_revoking_twice_counts_nothing_the_second_time():
    issued = sign_in()
    assert service.revoke_session(issued.session_id, RevokeReason.LOGOUT) == 1
    assert service.revoke_session(issued.session_id, RevokeReason.BLOCKED) == 0
    assert Session.objects.get().revoke_reason == RevokeReason.LOGOUT


def test_tokens_and_hashes_never_reach_the_log(caplog):
    issued = sign_in()
    second = service.refresh_session(issued.refresh_token, "company")
    with pytest.raises(NotAuthenticated):
        service.refresh_session(issued.refresh_token, "company")  # reuse is logged
    service.revoke_user_sessions(7, RevokeReason.LOGOUT)
    # Checked on the raw records: the log formatter's scrubbing is only a second layer.
    output = " ".join(f"{record.getMessage()} {record.args}" for record in caplog.records)
    assert "presented again" in output
    for secret in (issued.access_token, issued.refresh_token, second.refresh_token):
        assert secret not in output
    assert Session.objects.get().refresh_token_hash not in output
