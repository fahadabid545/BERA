"""The admin's view of companies: a searchable list and one company's page.

Both admin roles use it (`company.view`). It holds account, billing, usage and project facts
only: a project is shown by its title, status and the reading setup pinned at creation, never by
its job description, and nothing from a CV or a candidate is read here, so nothing of that kind
can reach an admin through it. The company's history is its audit entries (kinds and reasons).
"""

from adminusers.role_matrix import roles_allowed
from audit.models import AuditEvent
from companies.models import Company, CompanyUser
from core.errors import form_error
from plans import limits, summary
from plans.models import Plan, Subscription
from plans.subscriptions import FULL_ACCESS_STATES, effective_state, get_subscription
from platform_settings.service import get_setting
from projects.models import Project
from usage import service as usage

NO_PLAN = "none"
USAGE_LEVELS = ("under", "between", "reached")


def _measure_cvs(company_id):
    """CVs used this period against the company's own limit, or None when it has no active
    plan or no CV limit (there is nothing to measure against)."""
    subscription = get_subscription(company_id)
    used = usage.current_usage(company_id)["cvs_scored"] + usage.waiting_cvs(company_id)
    limit = limits.limit_for(company_id, limits.CVS_PER_MONTH)
    active = effective_state(subscription) in FULL_ACCESS_STATES
    return {"used": used, "limit": limit, "measurable": bool(active and limit)}


def _level(figures):
    """Under the first warning percent, between the first and the last, or at the last (100)."""
    reached = summary.warning_level(figures["used"], figures["limit"])
    percents = sorted(get_setting("usage.warning_percents"))
    if reached is None:
        return "under"
    return "reached" if reached == percents[-1] else "between"


def _checked_filters(params):
    status = params.get("status") or ""
    if status and status not in Company.Status.values:
        raise form_error({"status": "Choose a known status."})
    level = params.get("usage") or ""
    if level and level not in USAGE_LEVELS:
        raise form_error({"usage": "Choose a known usage level."})
    plan = params.get("plan") or ""
    if plan and plan != NO_PLAN and not plan.isdigit():
        raise form_error({"plan": "Choose a known plan."})
    try:
        page = max(int(params.get("page") or 1), 1)
    except ValueError as error:
        raise form_error({"page": "The page must be a number."}) from error
    return {
        "search": (params.get("search") or "").strip(),
        "status": status,
        "plan": plan,
        "country": (params.get("country") or "").strip().upper(),
        "usage": level,
        "page": page,
    }


def _matching(filters):
    companies = Company.objects.all()
    if filters["search"]:
        companies = companies.filter(name__icontains=filters["search"])
    if filters["status"]:
        companies = companies.filter(status=filters["status"])
    if filters["country"]:
        companies = companies.filter(country=filters["country"])
    if filters["plan"] == NO_PLAN:
        with_plan = Subscription.objects.filter(plan__isnull=False).values("company_id")
        companies = companies.exclude(pk__in=with_plan)
    elif filters["plan"]:
        on_plan = Subscription.objects.filter(plan_id=int(filters["plan"])).values("company_id")
        companies = companies.filter(pk__in=on_plan)
    return companies.order_by("name", "id")


def _describe_row(company, figures):
    subscription = get_subscription(company.pk)
    return {
        "id": str(company.pk),
        "name": company.name,
        "country": company.country,
        "status": company.status,
        "plan_name": subscription.plan.name if subscription.plan else None,
        "subscription_state": effective_state(subscription),
        "cvs_used": figures["used"],
        "cvs_limit": figures["limit"],
        "users": CompanyUser.objects.filter(company=company)
        .exclude(status=CompanyUser.Status.REMOVED)
        .count(),
        "created_at": company.created_at.isoformat(),
    }


def list_companies(params):
    filters = _checked_filters(params)
    companies = list(_matching(filters))
    figures = {}
    if filters["usage"]:
        # The usage filter needs every candidate's figures; without it only the page is measured.
        kept = []
        for company in companies:
            measured = _measure_cvs(company.pk)
            if measured["measurable"] and _level(measured) == filters["usage"]:
                figures[company.pk] = measured
                kept.append(company)
        companies = kept
    size = get_setting("admin_companies.page_size")
    first = (filters["page"] - 1) * size
    shown = companies[first : first + size]
    rows = [_describe_row(c, figures.get(c.pk) or _measure_cvs(c.pk)) for c in shown]
    return {
        "results": rows,
        "page": filters["page"],
        "page_size": size,
        "total": len(companies),
        "pages": max(1, -(-len(companies) // size)),
        "plans": [
            {"id": str(plan.pk), "name": plan.name} for plan in Plan.objects.order_by("name", "id")
        ],
    }


def _describe_user(person):
    return {
        "id": str(person.pk),
        "name": person.name,
        "email": person.email,
        "role": person.role,
        "status": person.status,
    }


def _describe_project(project):
    return {
        "id": str(project.pk),
        "title": project.title,
        "status": project.status,
        "reading_model": project.reading_model,
        "reading_prompt_version": project.reading_prompt_version,
        "created_at": project.created_at.isoformat(),
    }


def _describe_entry(entry):
    return {
        "id": entry.pk,
        "kind": entry.kind,
        "actor_kind": entry.actor_kind,
        "reason": entry.reason,
        "created_at": entry.created_at.isoformat(),
    }


def _subscription_and_usage(company_id, role):
    """The company's plan figures. The AI cost is money, which support never sees."""
    figures = summary.plan_and_usage(company_id)
    subscription = {
        name: figures[name]
        for name in ("plan_name", "state", "renewal", "grace_ends_at", "period_start", "period_end")
    }
    usage_figures = {name: figures[name] for name in ("cvs", "tokens", "projects")}
    if role in roles_allowed("ai.view"):
        usage_figures["estimated_cost"] = figures["estimated_cost"]
    return subscription, usage_figures


def company_detail(company, role):
    shown = get_setting("admin_companies.detail_limit")
    projects = Project.objects.filter(company_id=company.pk)
    subscription, usage_figures = _subscription_and_usage(company.pk, role)
    return {
        "company": {
            "id": str(company.pk),
            "name": company.name,
            "country": company.country,
            "status": company.status,
            "created_at": company.created_at.isoformat(),
            "deletion_due_at": company.deletion_due_at.isoformat()
            if company.deletion_due_at
            else None,
        },
        "users": [
            _describe_user(person)
            for person in CompanyUser.objects.filter(company=company).order_by("id")
        ],
        "subscription": subscription,
        "usage": usage_figures,
        "project_counts": {
            "active": projects.filter(status=Project.Status.ACTIVE).count(),
            "archived": projects.filter(status=Project.Status.ARCHIVED).count(),
        },
        "projects": [
            _describe_project(project)
            for project in projects.order_by("-created_at", "-id")[:shown]
        ],
        "history": [
            _describe_entry(entry)
            for entry in AuditEvent.objects.filter(company_id=company.pk).order_by(
                "-created_at", "-id"
            )[:shown]
        ],
    }
