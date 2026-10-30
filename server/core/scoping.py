"""The one place that decides whether a signed-in user may reach a company's record.

Both questions are answered here: does it belong to the user's company, and does the
user's role allow this. Anything outside the user's company, and anything that does not
exist or is not a valid identifier, gives the same "not found".
"""

from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework.exceptions import PermissionDenied

COMPANY_KIND = "company"


def get_in_company(queryset, company_id, *, company_field="company_id", **lookup):
    """Fetch one record of the given company.

    A record that does not exist, a record that belongs to another company and a malformed
    identifier all raise the same Http404, so the answer never reveals what exists.
    """
    try:
        return queryset.filter(**{company_field: company_id}).get(**lookup)
    except (queryset.model.DoesNotExist, ValidationError, ValueError, TypeError) as error:
        raise Http404 from error


def scope_to_company(queryset, user):
    """The records of the user's own company; other kinds of user have no company data here."""
    if user.kind != COMPANY_KIND or user.company_id is None:
        raise PermissionDenied()
    return queryset.filter(company_id=user.company_id)


def require_role(user, allowed_roles):
    """`allowed_roles` of None means every role of the company may do this."""
    if allowed_roles is not None and user.role not in allowed_roles:
        raise PermissionDenied()


def get_company_object(queryset, user, *, allowed_roles=None, **lookup):
    # Company first: a record of another company is "not found" whatever the user's role.
    record = get_in_company(scope_to_company(queryset, user), user.company_id, **lookup)
    require_role(user, allowed_roles)
    return record
