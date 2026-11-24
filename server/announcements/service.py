"""Announcement banners: what admins write, and what each company's people are shown.

A banner is shown from its start to its end, so an expired or not yet started one is never shown.
The ones shown are ordered newest first (by when they were written). Closing a banner is a choice
of one person: it stays shown to everyone else.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from audit.service import record
from companies.models import Company
from core.errors import form_error, not_found
from plans import subscriptions
from plans.models import Plan, Subscription

from .models import Announcement, AnnouncementDismissal

SCHEDULED, LIVE, EXPIRED = "scheduled", "live", "expired"


def status_of(announcement, now=None):
    now = now or timezone.now()
    if announcement.ends_at <= now:
        return EXPIRED
    return SCHEDULED if announcement.starts_at > now else LIVE


def _current_plan_id(company_id):
    """The plan a company is on now, or nothing when it has none or it has ended. Reading it
    never creates a subscription row."""
    subscription = Subscription.objects.filter(company_id=company_id).first()
    if subscription is None or subscription.plan_id is None:
        return None
    if subscriptions.effective_state(subscription) == Subscription.State.EXPIRED:
        return None
    return subscription.plan_id


def _live_for(company_id):
    """The banners that are on now and aimed at this company, whoever closed them."""
    now = timezone.now()
    aimed_at_company = Q(target=Announcement.Target.EVERYONE) | Q(
        target=Announcement.Target.COMPANIES, companies=company_id
    )
    plan_id = _current_plan_id(company_id)
    if plan_id is not None:
        aimed_at_company |= Q(target=Announcement.Target.PLAN, plan_id=plan_id)
    return (
        Announcement.objects.filter(starts_at__lte=now, ends_at__gt=now)
        .filter(aimed_at_company)
        .distinct()
    )


def shown_to(person):
    """The banners this person should see now, newest first."""
    closed = AnnouncementDismissal.objects.filter(user=person).values("announcement_id")
    shown = _live_for(person.company_id).exclude(pk__in=closed)
    ordered = shown.order_by("-created_at", "-id")
    return [{"id": item.pk, "message": item.message} for item in ordered]


def dismiss(person, announcement_id):
    """Closes a banner for this person. Closing one twice is fine; one that is not on for the
    person's company (or does not exist) is Not found, as if it did not exist."""
    banner = _live_for(person.company_id).filter(pk=announcement_id).first()
    if banner is None:
        raise not_found()
    AnnouncementDismissal.objects.get_or_create(
        announcement=banner, user=person, defaults={"company_id": person.company_id}
    )


def _as_admin_item(announcement, now):
    return {
        "id": announcement.pk,
        "message": announcement.message,
        "starts_at": announcement.starts_at,
        "ends_at": announcement.ends_at,
        "target": announcement.target,
        "plan_id": announcement.plan_id,
        "plan": announcement.plan.name if announcement.plan_id else None,
        "company_ids": sorted(company.pk for company in announcement.companies.all()),
        "status": status_of(announcement, now),
    }


def list_for_admin():
    """Every banner, newest first, with the plans and companies a banner can be aimed at."""
    now = timezone.now()
    items = Announcement.objects.select_related("plan").prefetch_related("companies")
    return {
        "items": [_as_admin_item(item, now) for item in items],
        "plans": list(Plan.objects.order_by("display_order", "id").values("id", "name")),
        "companies": list(Company.objects.order_by("name", "id").values("id", "name")),
    }


def _save(announcement, values):
    announcement.message = values["message"]
    announcement.starts_at = values["starts_at"]
    announcement.ends_at = values["ends_at"]
    announcement.target = values["target"]
    announcement.plan_id = values.get("plan")
    announcement.save()
    # Companies only matter for that target, so a changed target leaves none behind.
    is_chosen = announcement.target == Announcement.Target.COMPANIES
    announcement.companies.set(values.get("companies", []) if is_chosen else [])


def create_announcement(admin, values):
    ensure_known(values)
    with transaction.atomic():
        announcement = Announcement()
        _save(announcement, values)
        record(
            "admin.announcement_created",
            actor=admin,
            details={"announcement_id": announcement.pk, "target": announcement.target},
        )
    return announcement


def _changed_fields(announcement, values):
    old_companies = {company.pk for company in announcement.companies.all()}
    changed = [
        name
        for name in ("message", "starts_at", "ends_at", "target")
        if getattr(announcement, name) != values[name]
    ]
    if announcement.plan_id != values.get("plan"):
        changed.append("plan")
    if old_companies != set(values.get("companies", [])):
        changed.append("companies")
    return changed


def update_announcement(admin, announcement_id, values):
    ensure_known(values)
    with transaction.atomic():
        announcement = Announcement.objects.select_for_update().filter(pk=announcement_id).first()
        if announcement is None:
            raise not_found()
        changed = _changed_fields(announcement, values)
        _save(announcement, values)
        record(
            "admin.announcement_edited",
            actor=admin,
            details={"announcement_id": announcement.pk, "changed": ", ".join(changed)},
        )
    return announcement


def delete_announcement(admin, announcement_id):
    with transaction.atomic():
        announcement = Announcement.objects.filter(pk=announcement_id).first()
        if announcement is None:
            raise not_found()
        announcement.delete()
        record(
            "admin.announcement_deleted",
            actor=admin,
            details={"announcement_id": announcement_id},
        )


def ensure_known(values):
    """A plan or company that does not exist is a form mistake, not a server error."""
    if values.get("plan") is not None and not Plan.objects.filter(pk=values["plan"]).exists():
        raise form_error({"plan": "Choose a plan from the list."})
    chosen = set(values.get("companies", []))
    if chosen and Company.objects.filter(pk__in=chosen).count() != len(chosen):
        raise form_error({"companies": "Choose companies from the list."})
