"""Reading the audit log: filtered pages, and a CSV export that is itself recorded.

The log can hold millions of entries, so a page never counts the whole log and never skips rows
with an offset: entries are ordered newest first and the next page starts after a cursor (the time
and id of the last entry shown), which the indexes serve directly. A filter by person, company,
action or dates narrows the same way. An export refuses to start when more than
`audit_log.export_max_rows` entries match, and writes in chunks so memory stays small.
"""

import csv
import io
import json
from datetime import UTC, datetime, time, timedelta

from django.db.models import Q

from adminusers.models import AdminUser
from companies.models import Company, CompanyUser
from core.errors import AppError, form_error
from core.spreadsheets import safe_cell
from platform_settings.service import get_setting

from .events import KINDS
from .models import AuditEvent
from .service import record

MIN_PERSON_SEARCH = 3
MAX_PEOPLE_MATCHED = 200
EXPORT_CHUNK = 1000
EXPORT_COLUMNS = [
    "Time (UTC)",
    "Action",
    "Person type",
    "Person ID",
    "Person",
    "Company ID",
    "Company",
    "Target type",
    "Target ID",
    "Reason",
    "Details",
]
TOO_LARGE_CODE = "audit_export_too_large"


def actions():
    return sorted(KINDS)


def _day_start(day):
    return datetime.combine(day, time.min, tzinfo=UTC)


def _matching_people(text):
    """Admins and company people whose name or email contains `text`."""
    match = Q(name__icontains=text) | Q(email__icontains=text)
    admins = AdminUser.objects.filter(match).values_list("pk", flat=True)[:MAX_PEOPLE_MATCHED]
    people = CompanyUser.objects.filter(match).values_list("pk", flat=True)[:MAX_PEOPLE_MATCHED]
    return list(admins), list(people)


def filtered(filters):
    """The entries matching the filters (all optional), newest first."""
    entries = AuditEvent.objects.all()
    if person := filters.get("person"):
        if len(person) < MIN_PERSON_SEARCH:
            raise form_error({"person": f"Type at least {MIN_PERSON_SEARCH} letters."})
        admins, people = _matching_people(person)
        entries = entries.filter(
            Q(actor_kind=AuditEvent.ActorKind.ADMIN, actor_id__in=admins)
            | Q(actor_kind=AuditEvent.ActorKind.COMPANY, actor_id__in=people)
        )
    if filters.get("company") is not None:
        entries = entries.filter(company_id=filters["company"])
    if filters.get("action"):
        entries = entries.filter(kind=filters["action"])
    if filters.get("from_date"):
        entries = entries.filter(created_at__gte=_day_start(filters["from_date"]))
    if filters.get("to_date"):
        entries = entries.filter(created_at__lt=_day_start(filters["to_date"] + timedelta(days=1)))
    return entries.order_by("-created_at", "-id")


def _cursor_of(entry):
    return f"{entry.created_at.isoformat()}|{entry.pk}"


def _after(entries, cursor):
    try:
        stamp, pk = cursor.rsplit("|", 1)
        moment, pk = datetime.fromisoformat(stamp), int(pk)
    except ValueError:
        raise form_error({"cursor": "This page marker is not valid."}) from None
    return entries.filter(Q(created_at__lt=moment) | Q(created_at=moment, pk__lt=pk))


def _names(entries):
    """{("admin", id): name, ("company", id): name} for the people and companies in `entries`."""
    admin_ids = {e.actor_id for e in entries if e.actor_kind == AuditEvent.ActorKind.ADMIN}
    person_ids = {e.actor_id for e in entries if e.actor_kind == AuditEvent.ActorKind.COMPANY}
    company_ids = {e.company_id for e in entries if e.company_id is not None}
    names = {("admin", pk): name for pk, name in _pairs(AdminUser, admin_ids)}
    names |= {("company_user", pk): name for pk, name in _pairs(CompanyUser, person_ids)}
    names |= {("company", pk): name for pk, name in _pairs(Company, company_ids)}
    return names


def _pairs(model, ids):
    return model.objects.filter(pk__in=ids).values_list("pk", "name") if ids else []


def _person_of(entry, names):
    if entry.actor_kind == AuditEvent.ActorKind.NONE or entry.actor_id is None:
        return {"kind": "none", "id": None, "name": ""}
    key = "admin" if entry.actor_kind == AuditEvent.ActorKind.ADMIN else "company_user"
    return {
        "kind": entry.actor_kind,
        "id": entry.actor_id,
        "name": names.get((key, entry.actor_id), ""),
    }


def _row(entry, names):
    return {
        "id": entry.pk,
        "at": entry.created_at,
        "action": entry.kind,
        "person": _person_of(entry, names),
        "company_id": entry.company_id,
        "company": names.get(("company", entry.company_id), ""),
        "target_kind": entry.target_kind,
        "target_id": entry.target_id,
        "reason": entry.reason,
        "details": entry.details,
    }


def page(filters, cursor=None):
    """One page of entries and where the next one starts (null at the end). One more entry than
    the page holds is read, which says whether there is a next page without counting."""
    size = get_setting("audit_log.page_size")
    entries = filtered(filters)
    if cursor:
        entries = _after(entries, cursor)
    found = list(entries[: size + 1])
    shown = found[:size]
    names = _names(shown)
    return {
        "items": [_row(entry, names) for entry in shown],
        "next": _cursor_of(shown[-1]) if len(found) > size else None,
        "actions": actions(),
    }


def _filters_text(filters):
    """The filters as a short plain text for the audit entry of an export. What was typed to find
    a person is never kept: only that a person search was used."""
    parts = []
    if filters.get("person"):
        parts.append("person search")
    for name in ("company", "action", "from_date", "to_date"):
        if filters.get(name) not in (None, ""):
            parts.append(f"{name}={filters[name]}")
    return "; ".join(parts) or "none"


def _csv_chunk(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return out.getvalue()


def export(admin, filters):
    """Starts an export: returns a generator of CSV text. The export is recorded first, with who,
    which filters and how many rows, so it is in the log even if the download is cut short. It
    holds the entries that existed when it began (not its own entry)."""
    limit = get_setting("audit_log.export_max_rows")
    entries = filtered(filters)
    newest = entries.values_list("pk", flat=True).first()
    count = entries.values("pk")[: limit + 1].count() if newest is not None else 0
    if count > limit:
        raise AppError(
            TOO_LARGE_CODE,
            f"More than {limit} entries match. Narrow the dates or filters and try again.",
            status_code=400,
        )
    record(
        "admin.audit_log_exported",
        actor=admin,
        details={"filters": _filters_text(filters), "rows": count},
    )
    # The entries that existed before this export, and so not the entry just written for it.
    snapshot = entries.filter(pk__lte=newest) if newest is not None else entries.none()
    return _stream(snapshot)


def _stream(entries):
    yield _csv_chunk([EXPORT_COLUMNS])
    chunk = []
    for entry in entries.iterator(chunk_size=EXPORT_CHUNK):
        chunk.append(entry)
        if len(chunk) == EXPORT_CHUNK:
            yield _csv_chunk(_export_rows(chunk))
            chunk = []
    if chunk:
        yield _csv_chunk(_export_rows(chunk))


def _export_rows(entries):
    names = _names(entries)
    for entry in entries:
        row = _row(entry, names)
        yield [
            entry.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            entry.kind,
            row["person"]["kind"],
            row["person"]["id"],
            row["person"]["name"],
            entry.company_id,
            row["company"],
            entry.target_kind,
            entry.target_id,
            entry.reason,
            json.dumps(entry.details, sort_keys=True),
        ]
