"""Shared helpers for candidate data, which is sensitive personal data everywhere.

- Masking: show a contact detail in part wherever the full value is not required. The full
  value is shown only where a person really needs it (the recruiter's own contact view).
- Access blocking: `CandidateDataOnly` lets only company sign-ins reach candidate content;
  admin and support staff are refused whatever their role. Any exception would be its own,
  explicit, time-limited and audited feature (audit kind `admin.candidate_data_exception`).
- Log scrubbing lives in `core/logging_setup.py` (`redact`), the second layer behind the rule
  that candidate data is never passed to a logger, an email or analytics at all.
"""

import re

from rest_framework.permissions import BasePermission

from signin.kinds import COMPANY

from .errors import AppError

MASK = "***"
VISIBLE_PHONE_DIGITS = 4
MINIMUM_PHONE_DIGITS_TO_SHOW_ANY = VISIBLE_PHONE_DIGITS + 1


def mask_email(email):
    """'jane@example.com' becomes 'j***@example.com'."""
    local, separator, domain = (email or "").strip().partition("@")
    if not separator or not local or not domain:
        return MASK if email else ""
    return f"{local[0]}{MASK}@{domain}"


def mask_phone(phone):
    """Only the last four digits stay: '+1 (555) 010-2030' becomes '*******2030'."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if len(digits) < MINIMUM_PHONE_DIGITS_TO_SHOW_ANY:
        return "*" * len(digits)
    return "*" * (len(digits) - VISIBLE_PHONE_DIGITS) + digits[-VISIBLE_PHONE_DIGITS:]


def mask_name(name):
    """Initials only: 'Jane Example' becomes 'J. E.'."""
    return " ".join(f"{word[0].upper()}." for word in (name or "").split())


def mask_address(address):
    """An address is never shown in part."""
    return MASK if (address or "").strip() else ""


def mask_contact(contact):
    """The four contact fields of a `CvContact` (or a dict), all masked."""

    def field(name):
        return contact.get(name, "") if isinstance(contact, dict) else getattr(contact, name, "")

    return {
        "name": mask_name(field("name")),
        "email": mask_email(field("email")),
        "phone": mask_phone(field("phone")),
        "address": mask_address(field("address")),
    }


class CandidateDataOnly(BasePermission):
    """Refuses every sign-in that is not a company member's (so admin and support staff, whatever
    their role). Combine with `IsSignedIn`, which answers for a missing sign-in."""

    def has_permission(self, request, view):
        if getattr(request.user, "kind", None) == COMPANY:
            return True
        raise AppError(
            "candidate_data_blocked",
            "You do not have access to candidate data.",
            status_code=403,
        )
