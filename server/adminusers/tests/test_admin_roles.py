import pytest
from rest_framework.test import APIClient

from adminusers.admin_accounts import LAST_SUPER_ADMIN, change_role, set_status
from adminusers.models import AdminUser
from adminusers.role_matrix import ROLES_ALLOWED, roles_allowed
from core.errors import AppError
from core.tests.factories import make_admin_user, make_company_user, start_session_for
from signin import service

pytestmark = pytest.mark.django_db
REASON = "Fake reason for the test."

# The matrix as BERA-093 states it, written out again on purpose: changing a rule in
# role_matrix.py must also change this list, so a rule never changes by accident.
SUPPORT_MAY = [
    "company.view",
    "usage.view",
    "job.view",
    "job.retry",
    "job.cancel",
    "team_member.block",
    "data_request.handle",
    "announcement.read",
]
SUPPORT_MAY_NOT = [
    "plan.change",
    "price.change",
    "model.change",
    "prompt.change",
    "settings.change",
    "limit.change",
    "subscription.grant_free",
    "subscription.terminate",
    "company.suspend",
    "company_user.two_step_off",
    "admin_user.manage",
    "advanced.open",
    "plan.view",
    "ai.view",
    "payment.view",
    "settings.view",
    "audit_log.view",
    "admin_user.view",
]


def client_for(admin):
    issued = service.start_session(user_id=admin.pk, role=admin.role, company_id=None, kind="admin")
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")


def do(client, action):
    return client.post(f"/api/actions/{action}/")


@pytest.fixture(autouse=True)
def stand_in_routes(settings):
    settings.ROOT_URLCONF = "adminusers.tests.urls_for_roles"


def test_the_test_lists_cover_every_action_of_the_matrix_exactly():
    assert sorted(SUPPORT_MAY + SUPPORT_MAY_NOT) == sorted(ROLES_ALLOWED)


@pytest.mark.parametrize("action", sorted(ROLES_ALLOWED))
def test_a_super_admin_can_do_everything(action):
    response = do(client_for(make_admin_user(role="super")), action)
    assert (response.status_code, response.json()) == (200, {"done": action})


@pytest.mark.parametrize("action", SUPPORT_MAY)
def test_support_can_do_what_support_may(action):
    assert do(client_for(make_admin_user(role="support")), action).status_code == 200


@pytest.mark.parametrize("action", SUPPORT_MAY_NOT)
def test_support_is_refused_when_requesting_a_super_admin_action_directly(action):
    response = do(client_for(make_admin_user(role="support")), action)
    assert (response.status_code, response.json()["error"]["code"]) == (403, "not_allowed")


@pytest.mark.parametrize("action", sorted(ROLES_ALLOWED))
def test_visitors_and_company_sign_ins_are_refused_everything(action):
    assert do(APIClient(), action).status_code == 401
    person = make_company_user(role="owner")
    issued = start_session_for(
        user_id=person.pk, role="owner", company_id=person.company_id, kind="company"
    )
    company_client = APIClient(HTTP_AUTHORIZATION=f"Bearer {issued.access_token}")
    assert do(company_client, action).status_code == 401


def test_an_unknown_action_fails_loudly_instead_of_allowing_anything():
    with pytest.raises(KeyError):
        roles_allowed("plan.make_everything_free")


class TestChangesApplyAtOnce:
    def test_promoting_support_works_without_logging_in_again(self):
        admin = make_admin_user(role="support")
        client = client_for(admin)
        assert do(client, "plan.change").status_code == 403
        change_role(admin.pk, "super", by=admin, reason=REASON)
        assert do(client, "plan.change").status_code == 200

    def test_demoting_a_super_admin_takes_the_rights_away_with_the_same_token(self):
        make_admin_user(role="super")  # someone else stays
        admin = make_admin_user(role="super")
        client = client_for(admin)
        assert do(client, "admin_user.manage").status_code == 200
        change_role(admin.pk, "support", by=admin, reason=REASON)
        assert do(client, "admin_user.manage").status_code == 403
        assert do(client, "job.retry").status_code == 200

    def test_a_renewed_token_carries_the_current_role(self):
        admin = make_admin_user(role="support")
        issued = service.start_session(
            user_id=admin.pk, role="support", company_id=None, kind="admin"
        )
        AdminUser.objects.filter(pk=admin.pk).update(role="super")
        renewed = service.refresh_session(issued.refresh_token, "admin")
        client = APIClient(HTTP_AUTHORIZATION=f"Bearer {renewed.access_token}")
        assert do(client, "plan.change").status_code == 200

    def test_a_blocked_admin_loses_access_at_once(self):
        make_admin_user(role="super")
        admin = make_admin_user(role="super")
        client = client_for(admin)
        set_status(admin.pk, "blocked", by=admin, reason=REASON)
        assert do(client, "job.view").status_code == 401


class TestTheLastSuperAdmin:
    def test_the_only_super_admin_cannot_be_demoted(self):
        admin = make_admin_user(role="super")
        with pytest.raises(AppError) as error:
            change_role(admin.pk, "support", by=admin, reason=REASON)
        assert error.value.code == "last_super_admin" and error.value.message == LAST_SUPER_ADMIN
        admin.refresh_from_db()
        assert admin.role == "super"

    @pytest.mark.parametrize("status", ["removed", "blocked"])
    def test_the_only_super_admin_cannot_be_removed_or_blocked(self, status):
        admin = make_admin_user(role="super")
        make_admin_user(role="support")  # support does not count
        with pytest.raises(AppError) as error:
            set_status(admin.pk, status, by=admin, reason=REASON)
        assert error.value.code == "last_super_admin"
        admin.refresh_from_db()
        assert admin.status == "active"

    def test_blocked_or_removed_super_admins_do_not_count_as_another_one(self):
        admin = make_admin_user(role="super")
        make_admin_user(role="super", status="blocked")
        make_admin_user(role="super", status="removed")
        with pytest.raises(AppError):
            change_role(admin.pk, "support", by=admin, reason=REASON)

    def test_with_another_active_super_admin_the_change_is_allowed(self):
        admin = make_admin_user(role="super")
        make_admin_user(role="super")
        assert change_role(admin.pk, "support", by=admin, reason=REASON).role == "support"

    def test_two_super_admins_cannot_both_leave(self):
        first, second = make_admin_user(role="super"), make_admin_user(role="super")
        change_role(first.pk, "support", by=first, reason=REASON)
        with pytest.raises(AppError):
            set_status(second.pk, "removed", by=second, reason=REASON)

    def test_changes_that_keep_the_super_admin_are_fine(self):
        admin = make_admin_user(role="super")
        assert change_role(admin.pk, "super", by=admin, reason=REASON).role == "super"
        assert set_status(admin.pk, "active", by=admin, reason=REASON).status == "active"

    def test_support_can_be_removed_and_a_removed_super_admin_can_return(self):
        make_admin_user(role="super")
        support = make_admin_user(role="support")
        assert set_status(support.pk, "removed", by=support, reason=REASON).status == "removed"
        gone = make_admin_user(role="super", status="removed")
        assert set_status(gone.pk, "active", by=gone, reason=REASON).status == "active"
