"""What admin and support tools may know about a company's CVs: counts and statuses only.

Never a file name, CV text, profile or contact detail; those are candidate content, which staff
cannot open (see `core/personal_data.py`).
"""

from django.db.models import Count

from .models import CvFile


def cv_counts_by_status(company_id):
    """How many of the company's CVs are in each status, as `{status: count}` (every status is
    present, with 0 when there are none)."""
    counted = dict(
        CvFile.objects.filter(company_id=company_id)
        .values_list("status")
        .annotate(total=Count("id"))
        .order_by()
    )
    return {status: counted.get(status, 0) for status, _ in CvFile.Status.choices}
