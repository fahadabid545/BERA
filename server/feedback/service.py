"""Feedback from the people of a company, and how the admins work through it.

Nothing here writes the message to a log, an audit entry or an email: the admin overview only
counts what is new.
"""

from django.db import transaction

from audit.service import record
from core.errors import not_found
from platform_settings.service import get_setting

from .models import Feedback

Status = Feedback.Status


def send(person, values):
    """Saves what a signed-in person wrote. The company and the person come from the sign-in."""
    return Feedback.objects.create(
        company_id=person.company_id,
        user=person,
        kind=values["kind"],
        message=values["message"],
        page=values["page"],
    )


def new_count():
    return Feedback.objects.filter(status=Status.NEW).count()


def item_of(feedback, *, with_message=True):
    return {
        "id": str(feedback.pk),
        "company_id": feedback.company_id,
        "company": feedback.company.name,
        "user": feedback.user.name,
        "kind": feedback.kind,
        "page": feedback.page,
        "status": feedback.status,
        "note": feedback.note,
        "created_at": feedback.created_at.isoformat(),
        **({"message": feedback.message} if with_message else {}),
    }


def _newest(queryset):
    return queryset.select_related("company", "user").order_by("-created_at", "-pk")


def attention_items(limit):
    """The newest feedback nobody has looked at, for the admin overview (no message text)."""
    waiting = Feedback.objects.filter(status=Status.NEW)
    return {
        "total": waiting.count(),
        "items": [item_of(each, with_message=False) for each in _newest(waiting)[:limit]],
    }


def list_feedback(filters):
    found = Feedback.objects.all()
    if filters.get("status"):
        found = found.filter(status=filters["status"])
    if filters.get("kind"):
        found = found.filter(kind=filters["kind"])
    if filters.get("since"):
        found = found.filter(created_at__date__gte=filters["since"])
    if filters.get("until"):
        found = found.filter(created_at__date__lte=filters["until"])
    limit = get_setting("feedback.list_limit")
    return {
        "total": found.count(),
        "items": [item_of(each) for each in _newest(found)[:limit]],
    }


def update_feedback(admin, feedback_id, values):
    """Changes the status and/or the internal note; a change of status is recorded."""
    with transaction.atomic():
        feedback = Feedback.objects.select_for_update().filter(pk=feedback_id).first()
        if feedback is None:
            raise not_found()
        old_status = feedback.status
        feedback.status = values.get("status", old_status)
        if "note" in values:
            feedback.note = values["note"]
        feedback.save(update_fields=["status", "note"])
        if feedback.status != old_status:
            record(
                "admin.feedback_status_changed",
                actor=admin,
                company_id=feedback.company_id,
                details={
                    "feedback_id": str(feedback.pk),
                    "old_status": old_status,
                    "new_status": feedback.status,
                },
            )
    return feedback
