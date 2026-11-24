"""Data requests: logging them, moving them forward, and what is overdue.

A request goes Open, In progress, Completed and never back. Completing it saves the day. The due
date is fixed when the request is logged. One that is not completed and past its due day is
overdue.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from companies.models import Company
from core.errors import AppError, form_error, not_found
from platform_settings.service import get_setting

from .models import DataRequest

Status = DataRequest.Status
ORDER = [Status.OPEN, Status.IN_PROGRESS, Status.COMPLETED]
NOT_BACKWARDS_CODE = "data_request_status_backwards"
NOT_BACKWARDS_MESSAGE = "A request cannot go back to an earlier status."


def is_overdue(item, today=None):
    return item.status != Status.COMPLETED and item.due_on < (today or timezone.localdate())


def not_completed():
    return DataRequest.objects.exclude(status=Status.COMPLETED)


def open_count():
    return not_completed().count()


def item_of(item, names, today):
    return {
        "id": item.pk,
        "company_id": item.company_id,
        # The live name while the company exists, the one logged with the request after that.
        "company": names.get(item.company_id, item.company_name),
        "company_exists": item.company_id in names,
        "kind": item.kind,
        "requested_by": item.requested_by,
        "received_on": item.received_on,
        "due_on": item.due_on,
        "status": item.status,
        "completed_on": item.completed_on,
        "note": item.note,
        "overdue": is_overdue(item, today),
    }


def _items_of(requests):
    names = dict(
        Company.objects.filter(pk__in={each.company_id for each in requests}).values_list(
            "pk", "name"
        )
    )
    today = timezone.localdate()
    return [item_of(each, names, today) for each in requests]


def attention_items(limit):
    """The requests still to do, most urgent first, for the admin overview."""
    waiting = not_completed().order_by("due_on", "id")
    return {"total": waiting.count(), "items": _items_of(list(waiting[:limit]))}


def list_requests(status=None):
    """Not completed first, by due day; then the completed ones, newest first."""
    limit = get_setting("data_requests.list_limit")
    everything = DataRequest.objects.all()
    if status:
        everything = everything.filter(status=status)
    open_ones = list(everything.exclude(status=Status.COMPLETED).order_by("due_on", "id"))
    done = list(everything.filter(status=Status.COMPLETED).order_by("-completed_on", "-id"))
    shown = (open_ones + done)[:limit]
    return {
        "total": len(open_ones) + len(done),
        "items": _items_of(shown),
        "companies": list(Company.objects.order_by("name", "id").values("id", "name")),
    }


def create_request(admin, values):
    company = Company.objects.filter(pk=values["company"]).first()
    if company is None:
        raise form_error({"company": "Choose a company from the list."})
    due_on = values["received_on"] + timedelta(days=get_setting("data_requests.due_days"))
    with transaction.atomic():
        item = DataRequest.objects.create(
            company_id=company.pk,
            company_name=company.name,
            kind=values["kind"],
            requested_by=values["requested_by"],
            received_on=values["received_on"],
            due_on=due_on,
            note=values.get("note", ""),
        )
        record(
            "admin.data_request_created",
            actor=admin,
            company_id=company.pk,
            details={"request_id": item.pk, "request_type": item.kind},
        )
    return item


def update_request(admin, request_id, values):
    """Changes the status (forward only) and/or the note."""
    with transaction.atomic():
        item = DataRequest.objects.select_for_update().filter(pk=request_id).first()
        if item is None:
            raise not_found()
        new_status = values.get("status", item.status)
        if ORDER.index(new_status) < ORDER.index(item.status):
            raise AppError(NOT_BACKWARDS_CODE, NOT_BACKWARDS_MESSAGE, status_code=409)
        old_status = item.status
        if "note" in values:
            item.note = values["note"]
        if new_status != old_status:
            item.status = new_status
            if new_status == Status.COMPLETED:
                item.completed_on = timezone.localdate()
        item.save()
        if new_status != old_status:
            record(
                "admin.data_request_status_changed",
                actor=admin,
                company_id=item.company_id,
                details={"request_id": item.pk, "old_status": old_status, "new_status": new_status},
            )
    return item
