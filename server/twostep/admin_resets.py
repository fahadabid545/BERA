"""Super admins clear someone's two-step verification when they cannot use it any more.

An admin's authenticator is reset by another super admin (never the own one): the admin must
enrol again at the next login. A company user's is turned off after an identity check; the
person is emailed. Both end all of the person's sessions and are audited with the reason."""

from django.db import transaction

from adminusers.models import AdminUser
from audit.service import record
from companies.models import CompanyUser
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email
from signin import service as signin
from signin.kinds import ADMIN, COMPANY
from signin.service import RevokeReason

from .models import RecoveryCode

OWN_ACCOUNT = "You cannot reset your own two-step verification. Ask another super admin."
NOT_ON = "Two-step verification is not on for this account."
IDENTITY_NOT_CHECKED = "Confirm that the person's identity was checked first."
TITLE = "Two-step verification was turned off"
MESSAGE = (
    "Support turned off two-step verification on your account after checking your identity. "
    "You were signed out everywhere. If this was not you, contact support right away."
)


def _clear(person):
    person.two_step_enabled = False
    person.two_step_secret = ""
    person.two_step_last_step = None
    person.save(update_fields=["two_step_enabled", "two_step_secret", "two_step_last_step"])


def reset_admin_two_step(admin_id, *, by, reason):
    if by.pk == admin_id:
        raise AppError("own_account", OWN_ACCOUNT, status_code=403)
    with transaction.atomic():
        admin = AdminUser.objects.select_for_update().get(pk=admin_id)
        if not admin.two_step_enabled:
            raise AppError("two_step_not_on", NOT_ON, status_code=409)
        _clear(admin)
        signin.revoke_user_sessions(admin.pk, RevokeReason.TWO_STEP_RESET, kind=ADMIN)
        record("admin.two_step_reset", actor=by, target=admin, reason=reason)
    return admin


def turn_off_company_user_two_step(user_id, *, by, reason, identity_checked):
    if identity_checked is not True:
        raise AppError(
            "identity_not_checked",
            IDENTITY_NOT_CHECKED,
            status_code=400,
            fields={"identity_checked": IDENTITY_NOT_CHECKED},
        )
    with transaction.atomic():
        person = CompanyUser.objects.select_for_update().get(pk=user_id)
        if not person.two_step_enabled:
            raise AppError("two_step_not_on", NOT_ON, status_code=409)
        _clear(person)
        RecoveryCode.objects.filter(user=person).delete()
        signin.revoke_user_sessions(person.pk, RevokeReason.TWO_STEP_RESET, kind=COMPANY)
        record(
            "admin.company_two_step_off",
            actor=by,
            target=person,
            reason=reason,
            details={"identity_checked": True},
        )
        send_email(
            "account_notice",
            person.email,
            name=person.name,
            title=TITLE,
            message=MESSAGE,
            link=build_link("/login"),
        )
    return person
