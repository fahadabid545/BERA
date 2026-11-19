"""Deleting a whole company: the owner asks, a grace period follows, then everything is removed.

Asking needs the company's name typed exactly, and an active subscription must be acknowledged.
From then on nobody can sign in (the sessions end), and the owner gets an email with a link that
undoes it without signing in. After `account.deletion_grace_days` (14) a daily job removes
everything the company owns: its projects with their CVs, candidates and stored files, its
packages, shared reports, people, invitations, activity log, subscription and usage history.
Only the audit log stays, and it holds ids and kinds, never a name or an address. Backups are not
touched here; they age out under their own policy (see Daily backups).
"""

import importlib
import logging
from datetime import timedelta

from django.apps import apps
from django.db import models, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from audit.service import record as audit_record
from core.errors import AppError, form_error
from core.jobs import logged_job
from core.models import CompanyOwnedModel
from emailing.link_tokens import consume_link_token, issue_link_token, link_refusal
from emailing.links import build_link
from emailing.models import LinkToken
from emailing.rendering import format_moment
from emailing.service import send_email
from plans.subscriptions import FULL_ACCESS_STATES, status_of
from platform_settings.service import get_setting
from signin.models import Session

from .models import Company, CompanyUser, Invitation

logger = logging.getLogger(__name__)

PURPOSE = LinkToken.Purpose.UNDO_DELETION
NOT_ACTIVE = "This company cannot be deleted right now."
SUBSCRIPTION_ACTIVE = "subscription_active"
ENDED_TITLE = "Your company was deleted"
ENDED_MESSAGE = "Your company and everything in it were deleted, as you asked."
UNDONE_TITLE = "Your company will not be deleted"
UNDONE_MESSAGE = "The deletion of your company was undone. You can sign in again."

# Every module that registers project data or work to stop. A background job does not load the
# web routes that import them, so the removal imports them itself.
REGISTERING_MODULES = (
    "projects.requirements",
    "projects.scoring_settings",
    "projects.factor_settings",
    "cvs.service",
    "cvs.candidates",
    "cvs.processing",
    "cvs.shared_reports",
    "cvs.download_packages",
)
MAX_REMOVAL_PASSES = 10


def subscription_summary(company_id):
    """Whether a subscription still gives access, which the owner is warned about first."""
    current = status_of(company_id)
    active = current["state"] in FULL_ACCESS_STATES
    return {
        "active": active,
        "state": current["state"],
        "period_end": current["period_end"].isoformat() if current["period_end"] else None,
    }


def overview(company_id):
    return {"subscription": subscription_summary(company_id)}


def grace_days():
    return get_setting("account.deletion_grace_days")


def request_deletion(owner, company, confirm_name, acknowledge_subscription):
    """Starts the grace period for the company the owner belongs to. Nothing is removed yet."""
    if confirm_name != company.name:
        raise form_error({"confirm_name": "Type the company name exactly to confirm."})
    subscription = subscription_summary(company.pk)
    if subscription["active"] and not acknowledge_subscription:
        raise AppError(
            SUBSCRIPTION_ACTIVE,
            "Your company has an active subscription. Confirm to delete it anyway.",
            status_code=409,
            details={"state": subscription["state"], "period_end": subscription["period_end"]},
        )
    with transaction.atomic():
        locked = Company.objects.select_for_update().get(pk=company.pk)
        if locked.status != Company.Status.ACTIVE:
            raise AppError("company_not_active", NOT_ACTIVE, status_code=409)
        now = timezone.now()
        locked.status = Company.Status.PENDING_DELETION
        locked.deletion_requested_at = now
        locked.deletion_due_at = now + timedelta(days=grace_days())
        locked.save(update_fields=["status", "deletion_requested_at", "deletion_due_at"])
        token = issue_link_token(PURPOSE, owner.pk, grace_days() * 24)
        send_email(
            "deletion_scheduled",
            owner.email,
            name=owner.name,
            when=format_moment(locked.deletion_due_at),
            link=build_link("/undo-company-deletion", token=token),
        )
        audit_record("company.deletion_requested", actor=owner, target=locked)
    return {"due_at": locked.deletion_due_at.isoformat()}


def undo_deletion(token):
    """The link in the email: the company is active again. It works once and only while the
    grace period lasts."""
    owner_id = consume_link_token(token, PURPOSE)
    owner = CompanyUser.objects.select_related("company").filter(pk=owner_id).first()
    if owner is None:
        raise link_refusal("link_invalid", "This link is not valid.")
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=owner.company_id)
        if company.status != Company.Status.PENDING_DELETION:
            raise link_refusal("link_invalid", "This link is not valid.")
        company.status = Company.Status.ACTIVE
        company.deletion_requested_at = None
        company.deletion_due_at = None
        company.save(update_fields=["status", "deletion_requested_at", "deletion_due_at"])
        audit_record("company.deletion_undone", actor=None, target=company, company_id=company.pk)
        send_email(
            "account_notice",
            owner.email,
            name=owner.name,
            title=UNDONE_TITLE,
            message=UNDONE_MESSAGE,
            link=build_link("/login"),
        )
    return company


def _load_registrations():
    for module in REGISTERING_MODULES:
        importlib.import_module(module)


def _remove_projects(company_id):
    from projects import deletion
    from projects.models import Project

    for project in Project.objects.filter(company_id=company_id):
        for stop in deletion.WORK_STOPPERS.values():
            stop(company_id, project.pk)
        for remove in deletion.DATA_REMOVERS.values():
            remove(company_id, project.pk)
        project.delete()


def _remove_company_level_data(company_id):
    """What belongs to the company but to no project: the whole-company export packages, then
    every remaining row, in whatever order the links between them allow."""
    from cvs import download_packages
    from cvs.models import DownloadPackage

    for package in DownloadPackage.objects.filter(company_id=company_id, project__isnull=True):
        download_packages.remove_package_file(package)
    pending = [
        model
        for model in apps.get_models()
        if issubclass(model, CompanyOwnedModel)
        and not model._meta.abstract
        and "tests" not in model.__module__
    ]
    for _ in range(MAX_REMOVAL_PASSES):
        left = []
        for model in pending:
            try:
                with transaction.atomic():
                    model.objects.filter(company_id=company_id).delete()
            except ProtectedError:
                left.append(model)
        if not left:
            return
        pending = left
    names = ", ".join(sorted(model.__name__ for model in pending))
    raise RuntimeError(f"Company data could not be removed in order: {names}")


def _remove_people(company_id):
    people = list(CompanyUser.objects.filter(company_id=company_id).values_list("pk", flat=True))
    invitations = list(
        Invitation.objects.filter(company_id=company_id).values_list("pk", flat=True)
    )
    LinkToken.objects.filter(subject_id__in=people).exclude(
        purpose=LinkToken.Purpose.TEAM_INVITE
    ).delete()
    LinkToken.objects.filter(
        subject_id__in=invitations, purpose=LinkToken.Purpose.TEAM_INVITE
    ).delete()
    Session.objects.filter(company_id=company_id).delete()
    Invitation.objects.filter(company_id=company_id).delete()
    CompanyUser.objects.filter(company_id=company_id).delete()


def remove_company(company_id):
    """Removes the company and everything it owns, all or nothing. A file the store cannot delete
    stops it, and the daily job tries again."""
    _load_registrations()
    company = Company.objects.get(pk=company_id)
    owner = CompanyUser.objects.filter(
        company_id=company_id, role=CompanyUser.Role.OWNER, status=CompanyUser.Status.ACTIVE
    ).first()
    contact = (owner.email, owner.name) if owner else None
    with transaction.atomic():
        _remove_projects(company_id)
        _remove_company_level_data(company_id)
        _remove_people(company_id)
        audit_record("company.deleted", company_id=company_id, details={"company": company_id})
        models.Model.delete(company)  # the one allowed way past the block on `Company.delete`
    if contact:
        send_email(
            "account_notice",
            contact[0],
            name=contact[1],
            title=ENDED_TITLE,
            message=ENDED_MESSAGE,
            link=build_link("/"),
        )


@logged_job
def remove_due_companies():
    """Daily job: removes each company whose grace period has ended. Returns how many."""
    due = list(
        Company.objects.filter(
            status=Company.Status.PENDING_DELETION, deletion_due_at__lte=timezone.now()
        ).values_list("pk", flat=True)
    )
    removed = 0
    for company_id in due:
        try:
            remove_company(company_id)
        except Exception as error:
            # One company that cannot be removed yet must not stop the others; the daily run
            # tries it again. Only the kind of error is logged, never its data.
            logger.error(
                "A company due for deletion could not be removed yet (%s).", type(error).__name__
            )
            continue
        removed += 1
    return removed
