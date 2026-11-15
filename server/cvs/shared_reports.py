"""Sharing the top candidates with people who have no account.

A report is a frozen copy made when the link is created: the project's top candidates (as the
Top-N list has them now, ties included) with rank, score, grade, strengths and risks, and, unless
hidden, name, email and phone. Later scoring or stage changes never change it. The link holds a
long random token that is shown once; only its hash is stored, so a leaked database cannot
produce links. An unknown, expired or revoked link gets the same answer, so nothing tells them
apart. Each view of the page is counted.
"""

import json
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import Http404
from django.utils import timezone

from activity.service import record
from companies.models import CompanyUser
from core.errors import AppError, form_error
from platform_settings.service import get_setting
from projects.deletion import register_project_data
from signin.tokens import hash_token

from .models import SharedReport
from .top_list import top_scores

UNAVAILABLE_MESSAGE = "This report is no longer available."
TOKEN_BYTES = 32


def report_unavailable():
    return AppError("report_unavailable", UNAVAILABLE_MESSAGE, status_code=404)


def _entry(rank, score):
    return {
        "rank": rank,
        "score": f"{score.score:.1f}",
        "grade": score.grade,
        "strengths": score.strengths,
        "risks": score.risks,
    }


def _contacts(scores):
    return [
        {
            "name": item.candidate.contact.name,
            "email": item.candidate.contact.email,
            "phone": item.candidate.contact.phone,
        }
        for item in scores
    ]


def _checked_days(raw):
    choices = get_setting("sharing.report_link_choices_days")
    days = get_setting("sharing.report_link_default_days") if raw in (None, "") else raw
    if isinstance(days, bool) or days not in choices:
        raise form_error({"days": "Choose one of the offered times."})
    return days


def _person(project, user):
    return CompanyUser.objects.get(pk=user.user_id, company_id=project.company_id)


def create_report(project, user, raw_days, raw_hide_contact):
    """Makes the report and returns it with its token, which is never available again."""
    days = _checked_days(raw_days)
    if raw_hide_contact not in (None, True, False):
        raise form_error({"hide_contact": "Hiding contact details is yes or no."})
    hide_contact = bool(raw_hide_contact)
    scores = top_scores(project)
    if not scores:
        raise AppError(
            "nothing_to_share",
            "There are no scored candidates to share yet.",
            status_code=400,
        )
    person = _person(project, user)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    report = SharedReport.objects.create(
        company_id=project.company_id,
        project=project,
        created_by=person,
        token_hash=hash_token(token),
        project_title=project.title,
        entries=[_entry(rank, item) for rank, item in enumerate(scores, start=1)],
        contacts="" if hide_contact else json.dumps(_contacts(scores)),
        hide_contact=hide_contact,
        expires_at=timezone.now() + timedelta(days=days),
    )
    record(
        "share",
        company_id=project.company_id,
        actor=person,
        target_kind="project",
        target_id=project.pk,
        details={"action": "created", "days": days, "hide_contact": hide_contact},
    )
    return report, token


def status_of(report, now=None):
    if report.revoked_at is not None:
        return "revoked"
    return "expired" if report.expires_at <= (now or timezone.now()) else "active"


def describe(report):
    return {
        "id": str(report.pk),
        "created_at": report.created_at.isoformat(),
        "expires_at": report.expires_at.isoformat(),
        "hide_contact": report.hide_contact,
        "candidates": len(report.entries),
        "views": report.views,
        "status": status_of(report),
    }


def reports_of(project):
    """The project's report links, newest first, and the expiry times the sharer may choose."""
    reports = SharedReport.objects.filter(company_id=project.company_id, project=project)
    return {
        "days": {
            "choices": get_setting("sharing.report_link_choices_days"),
            "default": get_setting("sharing.report_link_default_days"),
        },
        "reports": [describe(report) for report in reports.order_by("-created_at", "-pk")],
    }


def revoke_report(project, user, report_id):
    """Stops the link at once. Revoking twice keeps the first time."""
    try:
        report = SharedReport.objects.get(
            company_id=project.company_id, project=project, pk=report_id
        )
    except (SharedReport.DoesNotExist, ValueError, ValidationError):
        raise Http404 from None
    if report.revoked_at is None:
        SharedReport.objects.filter(pk=report.pk, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        record(
            "share",
            company_id=project.company_id,
            actor=_person(project, user),
            target_kind="project",
            target_id=project.pk,
            details={"action": "revoked"},
        )
    report.refresh_from_db()
    return describe(report)


def view_report(token):
    """What the public page shows for a token, counting the view; the one "no longer available"
    answer for anything that is not a live report."""
    report = SharedReport.objects.filter(token_hash=hash_token(token)).first()
    if report is None or status_of(report) != "active":
        raise report_unavailable()
    SharedReport.objects.filter(pk=report.pk).update(views=F("views") + 1)
    contacts = [] if report.hide_contact else json.loads(report.contacts)
    entries = []
    for position, entry in enumerate(report.entries):
        shown = {**entry, "candidate": f"Candidate {entry['rank']}"}
        if not report.hide_contact:
            shown["contact"] = contacts[position]
        entries.append(shown)
    return {
        "title": report.project_title,
        "created_at": report.created_at.isoformat(),
        "expires_at": report.expires_at.isoformat(),
        "hide_contact": report.hide_contact,
        "entries": entries,
    }


def _remove_for_project(company_id, project_id):
    SharedReport.objects.filter(company_id=company_id, project_id=project_id).delete()


register_project_data("SharedReport", _remove_for_project)
