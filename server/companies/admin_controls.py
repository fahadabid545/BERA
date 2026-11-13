"""An admin suspends or unsuspends a company. Suspending ends every session of the company at
once (the shared revoke function); the company then sees the suspended message at sign-in."""

from django.db import transaction

from audit.service import record
from core.errors import AppError
from emailing.links import build_link
from emailing.service import send_email
from plans.subscriptions import owner_of
from signin import service as signin
from signin.service import RevokeReason

from .models import Company

ALREADY_SUSPENDED = "This company is already suspended."
NOT_SUSPENDED = "This company is not suspended."
SUSPENDED_TITLE = "Your company account was suspended"
SUSPENDED_MESSAGE = "Your company account was suspended. Please contact support."
RESTORED_TITLE = "Your company account is active again"
RESTORED_MESSAGE = "Your company account is active again. You can sign in."


def _tell_the_owner(company_id, title, message):
    owner = owner_of(company_id)
    if owner is not None:
        send_email(
            "account_notice",
            owner.email,
            name=owner.name,
            title=title,
            message=message,
            link=build_link("/login"),
        )


def suspend_company(company_id, *, by, reason):
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=company_id)
        if company.status == Company.Status.SUSPENDED:
            raise AppError("already_suspended", ALREADY_SUSPENDED, status_code=409)
        company.status = Company.Status.SUSPENDED
        company.save(update_fields=["status"])
        signin.revoke_company_sessions(company.pk, RevokeReason.COMPANY_SUSPENDED)
        record("admin.company_suspended", actor=by, target=company, reason=reason)
        _tell_the_owner(company.pk, SUSPENDED_TITLE, SUSPENDED_MESSAGE)
    return company


def unsuspend_company(company_id, *, by, reason):
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=company_id)
        if company.status != Company.Status.SUSPENDED:
            raise AppError("not_suspended", NOT_SUSPENDED, status_code=409)
        company.status = Company.Status.ACTIVE
        company.save(update_fields=["status"])
        record("admin.company_unsuspended", actor=by, target=company, reason=reason)
        _tell_the_owner(company.pk, RESTORED_TITLE, RESTORED_MESSAGE)
    return company
