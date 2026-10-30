from django.http import Http404


def get_in_company(queryset, company_id, *, company_field="company_id", **lookup):
    """Fetch one record of the given company.

    A record that does not exist and a record that belongs to another company raise
    the same Http404, so the answer never reveals that the other company's record exists.
    """
    try:
        return queryset.filter(**{company_field: company_id}).get(**lookup)
    except queryset.model.DoesNotExist as error:
        raise Http404 from error
