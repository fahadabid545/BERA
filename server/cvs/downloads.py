"""Letting a person download a CV they are allowed to see. The Downloads ticket adds the route
and buttons; this is the permission check and the link they use."""

import privatefiles
from companies.role_matrix import roles_allowed
from core.scoping import get_company_object

from .models import CvFile


def download_link_for_cv(user, cv_id):
    """A short-lived link to the CV (`{"url", "expires_at"}`) for a signed-in company user.
    The CV must belong to the user's own company and the user's role must allow downloads;
    anything else is "not found" or "not allowed", exactly as for any company record. Archived
    projects can still be downloaded from."""
    cv_file = get_company_object(
        CvFile.objects.all(), user, allowed_roles=roles_allowed("cv.download"), id=cv_id
    )
    return privatefiles.download_link(cv_file.storage_key, cv_file.original_name)
