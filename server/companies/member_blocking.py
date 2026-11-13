"""An admin blocks or unblocks one person inside a company. A blocked person is signed out at
once (every session ends) and cannot sign in until unblocked; the owner is emailed. The
company owner can never be blocked: suspend the company instead."""

from django.db import transaction

from audit.service import record
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email
from plans.subscriptions import owner_of
from signin import service as signin
from signin.kinds import COMPANY
from signin.service import RevokeReason

from .models import CompanyUser

OWNER_CANNOT_BE_BLOCKED = "The company owner cannot be blocked. Suspend the company instead."
ALREADY_BLOCKED = "This person is already blocked."
NOT_BLOCKED = "This person is not blocked."
REMOVED = "This person was removed from the company."


def _tell_the_owner(person, title, message):
    owner = owner_of(person.company_id)
    if owner is not None:
        send_email(
            "account_notice",
            owner.email,
            name=owner.name,
            title=title,
            message=message,
            link=build_link("/company/team"),
        )


def block_member(user_id, *, by, reason):
    with transaction.atomic():
        person = CompanyUser.objects.select_for_update().get(pk=user_id)
        if person.role == CompanyUser.Role.OWNER:
            raise AppError("owner_cannot_be_blocked", OWNER_CANNOT_BE_BLOCKED, status_code=409)
        if person.status == CompanyUser.Status.REMOVED:
            raise AppError("member_removed", REMOVED, status_code=409)
        if person.status == CompanyUser.Status.BLOCKED:
            raise AppError("already_blocked", ALREADY_BLOCKED, status_code=409)
        person.status = CompanyUser.Status.BLOCKED
        person.save(update_fields=["status"])
        signin.revoke_user_sessions(person.pk, RevokeReason.BLOCKED, kind=COMPANY)
        record("admin.member_blocked", actor=by, target=person, reason=reason)
        _tell_the_owner(
            person,
            "A team member was blocked",
            f"Support blocked {person.name}'s access to your company. They were signed out.",
        )
    return person


def unblock_member(user_id, *, by, reason):
    with transaction.atomic():
        person = CompanyUser.objects.select_for_update().get(pk=user_id)
        if person.status != CompanyUser.Status.BLOCKED:
            raise AppError("not_blocked", NOT_BLOCKED, status_code=409)
        person.status = CompanyUser.Status.ACTIVE
        person.save(update_fields=["status"])
        record("admin.member_unblocked", actor=by, target=person, reason=reason)
        _tell_the_owner(
            person,
            "A team member was unblocked",
            f"Support restored {person.name}'s access to your company.",
        )
    return person
