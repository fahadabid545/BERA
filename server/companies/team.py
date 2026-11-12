"""The owner managing the team: who is in it, removing a member, handing the company over."""

from django.db import transaction

from activity import service as activity
from audit.service import record
from core.errors import AppError
from core.scoping import get_in_company
from signin import guess_limit

from .models import CompanyUser
from .services import transfer_ownership

OWNER_CANNOT_LEAVE = "The owner cannot be removed. Hand the company to another member first."
ALREADY_REMOVED = "This person has already been removed."
WRONG_PASSWORD = "Your password is incorrect."


def team_members(company_id):
    """Everyone who is still part of the company (removed people are gone from the list)."""
    return (
        CompanyUser.objects.filter(company_id=company_id)
        .exclude(status=CompanyUser.Status.REMOVED)
        .order_by("created_at", "id")
    )


def remove_member(owner, member_id):
    """Takes a member out of the company. Saving the new status ends their sessions at once
    (signin/signals.py). Their work stays with the company; the activity log keeps the name
    they had."""
    with transaction.atomic():
        member = get_in_company(
            CompanyUser.objects.select_for_update(), owner.company_id, pk=member_id
        )
        if member.role == CompanyUser.Role.OWNER:  # also the owner removing themselves
            raise AppError("owner_cannot_be_removed", OWNER_CANNOT_LEAVE, status_code=409)
        if member.status == CompanyUser.Status.REMOVED:
            raise AppError("already_removed", ALREADY_REMOVED, status_code=409)
        member.status = CompanyUser.Status.REMOVED
        member.save(update_fields=["status"])
        record("team.member_removed", actor=owner, target=member)
        activity.record(
            "member_removed",
            company_id=owner.company_id,
            actor=owner,
            target_kind="company_user",
            target_id=member.pk,
            details={"removed_name": member.name},
        )
    return member


def _confirm_password(owner, password):
    """Wrong entries count toward the same pause as wrong guesses at the login page."""
    guess_limit.refuse_if_paused(owner.email)
    if not owner.check_password(password):
        guess_limit.record_failure(
            owner.email,
            AppError(
                "wrong_password",
                WRONG_PASSWORD,
                status_code=400,
                fields={"password": WRONG_PASSWORD},
            ),
        )
    guess_limit.forget_failures(owner.email)


def hand_over_company(owner, new_owner_id, password):
    """The owner becomes a member and the chosen active member becomes the owner. Needs the
    owner's password, so a stolen session alone cannot give the company away."""
    _confirm_password(owner, password)
    with transaction.atomic():
        new_owner = get_in_company(CompanyUser.objects.all(), owner.company_id, pk=new_owner_id)
        transfer_ownership(owner.company, new_owner)
        record("team.ownership_transferred", actor=owner, target=new_owner)
        activity.record(
            "ownership_transferred",
            company_id=owner.company_id,
            actor=owner,
            target_kind="company_user",
            target_id=new_owner.pk,
            details={"new_owner_name": new_owner.name},
        )
    return new_owner
