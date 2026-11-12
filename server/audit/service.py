"""Writing to the audit log. The only code that adds entries."""

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser, Invitation
from core.errors import AppError

from .events import KINDS
from .models import AuditEvent

MAX_REASON_LENGTH = 1000
MAX_DETAIL_LENGTH = 200
REASON_REQUIRED = "A written reason is required for this action."
# A detail whose name contains one of these could hold a secret or private text. Details are
# short facts such as an old and a new role, never the content of anything.
FORBIDDEN_NAME_PARTS = ("password", "token", "secret", "code", "cv", "text", "email", "hash", "key")
ALLOWED_VALUE_TYPES = (str, int, bool, type(None))


def _who(person):
    """(kind, id, company id) of an account, or of nobody."""
    if isinstance(person, AdminUser):
        return AuditEvent.ActorKind.ADMIN, person.pk, None
    if isinstance(person, CompanyUser):
        return AuditEvent.ActorKind.COMPANY, person.pk, person.company_id
    return AuditEvent.ActorKind.NONE, None, None


def _what(thing):
    """(kind, id, company id) of what an action was done to."""
    if isinstance(thing, AdminUser):
        return "admin_user", thing.pk, None
    if isinstance(thing, CompanyUser):
        return "company_user", thing.pk, thing.company_id
    if isinstance(thing, Company):
        return "company", thing.pk, thing.pk
    if isinstance(thing, Invitation):
        return "invitation", thing.pk, thing.company_id
    return "", "", None


def _checked_details(details):
    for name, value in details.items():
        if any(part in name.lower() for part in FORBIDDEN_NAME_PARTS):
            raise ValueError(f"The audit log must not hold a detail called {name!r}.")
        if not isinstance(value, ALLOWED_VALUE_TYPES) or len(str(value)) > MAX_DETAIL_LENGTH:
            raise ValueError(f"The audit detail {name!r} must be a short value.")
    return details


def record(kind, *, actor=None, target=None, company_id=None, reason="", details=None):
    """Adds one entry. `actor` and `target` are accounts, a company or an invitation (or
    left out). A kind that needs a reason without one is refused, so call this inside the
    same transaction as the change: a refusal then undoes the change too."""
    definition = KINDS[kind]  # an unknown kind is a mistake in the code, so it fails loudly
    reason = (reason or "").strip()
    if definition.reason_required and not reason:
        raise AppError(
            "reason_required", REASON_REQUIRED, status_code=400, fields={"reason": REASON_REQUIRED}
        )
    actor_kind, actor_id, actor_company = _who(actor)
    target_kind, target_id, target_company = _what(target)
    return AuditEvent.objects.create(
        kind=kind,
        actor_kind=actor_kind,
        actor_id=actor_id,
        company_id=company_id or actor_company or target_company,
        target_kind=target_kind,
        target_id=str(target_id) if target_id is not None else "",
        reason=reason[:MAX_REASON_LENGTH],
        details=_checked_details(details or {}),
    )
