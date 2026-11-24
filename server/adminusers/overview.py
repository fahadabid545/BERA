"""The admin overview: how the platform is doing, counted from stored data when asked.

One answer per card, for the chosen period next to the period before it (same length):

- cards: new companies, CVs scored, and (super admins) the AI cost.
- revenue (super admins): the estimated monthly revenue from the paying subscriptions, how it is
  split over plans and subscription states, and what is left after the AI cost. There are no
  payment records yet, so this is "what the active plans bring in a month", not money received.
- usage: the pace of scoring over time and the companies using the platform most.
- ai (super admins): how the AI calls went, by purpose and by model, and the token budget.
- pending: what waits for an admin.
- recent: the newest companies.

Support admins get the counts and the usage; money and AI figures are left out entirely, and the
routes behind them refuse support (`payment.view`, `ai.view`). `detail` lists what is behind a
card or mark; `report` is the same numbers as a plain table for the CSV and the printable page.
"""

import csv
import io
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.utils import timezone

from adminusers.role_matrix import roles_allowed
from ai import control
from ai.models import AiCall
from companies.models import Company
from core.errors import form_error
from core.scoping import require_role
from cvs import job_monitor
from cvs.charts import per_day, percent_change
from cvs.dashboard import card, checked_period, in_days, windows
from cvs.models import CandidateScore
from datarequests import service as data_requests
from plans.models import Plan, Subscription
from plans.subscriptions import State, effective_state
from platform_settings.service import get_setting

PERCENT = 100
COST_PLACES = 2
PAYING = (State.ACTIVE, State.PAST_DUE, State.CANCELLED)
STATES = tuple(state.value for state in State)
PURPOSES = tuple(purpose.value for purpose in AiCall.Purpose)
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _can(role, action):
    return role in roles_allowed(action)


def _money(value):
    return round(float(value or 0), COST_PLACES)


def _subscriptions():
    """Every company's subscription with the state access is decided on, in one query."""
    now = timezone.now()
    return [
        (subscription, effective_state(subscription, now))
        for subscription in Subscription.objects.select_related("plan", "company")
    ]


def _paying(subscriptions):
    return [
        (subscription, state)
        for subscription, state in subscriptions
        if state in PAYING and subscription.plan and subscription.plan.price_usd
    ]


def _daily_cost(first, days):
    found = dict(
        in_days(AiCall.objects.all(), "created_at", first, first + timedelta(days=days))
        .annotate(day=TruncDate("created_at"))
        .values_list("day")
        .annotate(total=Sum("estimated_cost"))
    )
    return [_money(found.get(first + timedelta(days=offset))) for offset in range(days)]


def _cost(first, end):
    return _money(
        in_days(AiCall.objects.all(), "created_at", first, end).aggregate(
            total=Sum("estimated_cost")
        )["total"]
    )


def _cards(role, start, before, end):
    spark = get_setting("dashboard.sparkline_days")
    spark_start = timezone.now().date() - timedelta(days=spark - 1)
    companies, scores = Company.objects.all(), CandidateScore.objects.all()
    cards = {
        "companies": card(
            in_days(companies, "created_at", start, end).count(),
            in_days(companies, "created_at", before, start).count(),
            per_day(companies, "created_at", spark_start, spark),
        ),
        "cvs_scored": card(
            in_days(scores, "created_at", start, end).count(),
            in_days(scores, "created_at", before, start).count(),
            per_day(scores, "created_at", spark_start, spark),
        ),
    }
    if _can(role, "ai.view"):
        now_cost, before_cost = _cost(start, end), _cost(before, start)
        cards["ai_cost"] = {
            "value": now_cost,
            "previous": before_cost,
            "change": percent_change(now_cost, before_cost),
            "series": _daily_cost(spark_start, spark),
        }
    return cards


def _totals(subscriptions):
    return {
        "companies": Company.objects.count(),
        "suspended": Company.objects.filter(status=Company.Status.SUSPENDED).count(),
        "paying": len(_paying(subscriptions)),
    }


def _revenue(subscriptions):
    paying = _paying(subscriptions)
    mrr = sum(float(subscription.plan.price_usd) for subscription, _ in paying)
    by_plan = {}
    for subscription, _ in paying:
        row = by_plan.setdefault(
            subscription.plan_id,
            {
                "id": subscription.plan_id,
                "name": subscription.plan.name,
                "subscribers": 0,
                "mrr": 0,
            },
        )
        row["subscribers"] += 1
        row["mrr"] += float(subscription.plan.price_usd)
    plans = sorted(by_plan.values(), key=lambda row: -row["mrr"])
    for row in plans:
        row["mrr"] = round(row["mrr"], COST_PLACES)
        row["share"] = round(row["mrr"] * PERCENT / mrr, 1) if mrr else 0
    states = dict.fromkeys(STATES, 0)
    for _, state in subscriptions:
        states[state] += 1
    states["no_plan"] += Company.objects.count() - len(subscriptions)
    margin_days = get_setting("admin_dashboard.margin_days")
    today = timezone.now().date()
    cost = _cost(today - timedelta(days=margin_days - 1), today + timedelta(days=1))
    return {
        "mrr": round(mrr, COST_PLACES),
        "ai_cost": cost,
        "margin_days": margin_days,
        "margin_percent": round((mrr - cost) * PERCENT / mrr, 1) if mrr else None,
        "plans": plans,
        "states": states,
    }


def _trend(series, days):
    today = timezone.now().date()
    start = today - timedelta(days=days - 1)
    before = start - timedelta(days=days)
    metrics = {}
    for name, queryset in series.items():
        current = per_day(queryset, "created_at", start, days)
        previous = per_day(queryset, "created_at", before, days)
        metrics[name] = {
            "current": current,
            "previous": previous,
            "total": sum(current),
            "previous_total": sum(previous),
            "change_percent": percent_change(sum(current), sum(previous)),
        }
    return {"days": days, "start": start.isoformat(), "metrics": metrics}


def _plans_of(company_ids):
    """{company id: (plan name or None, the state access is decided on)} for those companies; a
    company with no subscription row yet has no plan."""
    now = timezone.now()
    found = {
        subscription.company_id: (
            subscription.plan.name if subscription.plan else None,
            effective_state(subscription, now),
        )
        for subscription in Subscription.objects.filter(company_id__in=company_ids).select_related(
            "plan"
        )
    }
    return {pk: found.get(pk, (None, State.NO_PLAN.value)) for pk in company_ids}


def _company_rows(companies, extra=None):
    """Rows for companies already loaded, each with its plan and state."""
    plans = _plans_of([company.pk for company in companies])
    return [
        {
            "type": "company",
            "id": str(company.pk),
            "name": company.name,
            "country": company.country,
            "status": company.status,
            "plan": plans[company.pk][0],
            "state": plans[company.pk][1],
            **(extra or {}).get(company.pk, {}),
        }
        for company in companies
    ]


def _top_companies(role, start, end):
    limit = get_setting("admin_dashboard.top_companies_count")
    scored = list(
        in_days(CandidateScore.objects.all(), "created_at", start, end)
        .values("company")
        .annotate(total=Count("pk"))
        .order_by("-total")[:limit]
    )
    ids = [row["company"] for row in scored]
    companies = {company.pk: company for company in Company.objects.filter(pk__in=ids)}
    show_cost = _can(role, "ai.view")
    costs = {}
    if show_cost:
        costs = {
            row["company"]: row
            for row in in_days(AiCall.objects.filter(company_id__in=ids), "created_at", start, end)
            .values("company")
            .annotate(tokens=Sum("tokens_in") + Sum("tokens_out"), cost=Sum("estimated_cost"))
        }
    extra = {}
    for row in scored:
        extra[row["company"]] = {"cvs_scored": row["total"]}
        if show_cost:
            found = costs.get(row["company"], {})
            extra[row["company"]].update(
                tokens=found.get("tokens") or 0, cost=_money(found.get("cost"))
            )
    return _company_rows([companies[pk] for pk in ids], extra)


def _ai(start, end):
    calls = in_days(AiCall.objects.all(), "created_at", start, end)
    total = calls.count()
    failed = calls.filter(result=AiCall.Result.FAILED).count()
    by_purpose = dict(calls.values_list("purpose").annotate(total=Count("pk")))
    by_model = [
        {
            "model": row["model"],
            "calls": row["calls"],
            "tokens": row["tokens"] or 0,
            "cost": _money(row["cost"]),
        }
        for row in calls.values("model")
        .annotate(
            calls=Count("pk"),
            tokens=Sum("tokens_in") + Sum("tokens_out"),
            cost=Sum("estimated_cost"),
        )
        .order_by("-cost", "model")
    ]
    margin_days = get_setting("admin_dashboard.margin_days")
    today = timezone.now().date()
    recent = (
        in_days(
            AiCall.objects.all(),
            "created_at",
            today - timedelta(days=margin_days - 1),
            today + timedelta(days=1),
        ).aggregate(used=Sum("tokens_in") + Sum("tokens_out"))["used"]
        or 0
    )
    cap = sum(
        subscription.plan.monthly_ai_token_cap or 0
        for subscription, state in _subscriptions()
        if state in (*PAYING, State.GRANTED_FREE) and subscription.plan
    )
    return {
        "calls": {
            "total": total,
            "failed": failed,
            "failure_percent": round(failed * PERCENT / total, 1) if total else None,
        },
        "by_purpose": [
            {"purpose": purpose, "count": by_purpose.get(purpose, 0)} for purpose in PURPOSES
        ],
        "by_model": by_model,
        "tokens": {
            "used": recent,
            "cap": cap,
            "percent": round(recent * PERCENT / cap, 1) if cap else None,
            "days": margin_days,
        },
        "control": control.describe(),
    }


def _pending(role, subscriptions):
    now = timezone.now()
    horizon = now + timedelta(days=get_setting("admin_dashboard.expiring_grant_days"))
    pending = {
        "past_due": sum(1 for _, state in subscriptions if state == State.PAST_DUE),
        "grants_expiring": sum(
            1
            for subscription, state in subscriptions
            if state == State.GRANTED_FREE
            and subscription.period_end
            and subscription.period_end <= horizon
        ),
        "suspended": Company.objects.filter(status=Company.Status.SUSPENDED).count(),
    }
    if _can(role, "ai.view"):
        pending["failed_ai_calls"] = _failed_calls(now).count()
    if _can(role, "job.view"):
        pending["failed_jobs"] = job_monitor.failed_count()
    if _can(role, "data_request.handle"):
        pending["data_requests"] = data_requests.open_count()
    return pending


def _failed_calls(now):
    return AiCall.objects.filter(
        result=AiCall.Result.FAILED,
        created_at__gte=now - timedelta(hours=get_setting("admin_dashboard.failed_calls_hours")),
    )


def _recent_companies():
    limit = get_setting("admin_dashboard.recent_companies_count")
    companies = list(Company.objects.order_by("-created_at")[:limit])
    return [
        {**row, "created_at": company.created_at.isoformat()}
        for row, company in zip(_company_rows(companies), companies, strict=True)
    ]


def overview(role, raw_days):
    days = checked_period(raw_days)
    start, before, end = windows(days)
    subscriptions = _subscriptions()
    body = {
        "refresh_seconds": get_setting("live_updates.max_delay_seconds"),
        "role": role,
        "days": days,
        "choices": get_setting("dashboard.period_choices_days"),
        "cards": _cards(role, start, before, end),
        "totals": _totals(subscriptions),
        "usage": {
            "trend": _trend(
                {
                    "cvs_scored": CandidateScore.objects.all(),
                    **({"ai_calls": AiCall.objects.all()} if _can(role, "ai.view") else {}),
                },
                days,
            ),
            "top_companies": _top_companies(role, start, end),
        },
        "pending": _pending(role, subscriptions),
        "recent": _recent_companies(),
    }
    if _can(role, "payment.view"):
        body["revenue"] = _revenue(subscriptions)
    if _can(role, "ai.view"):
        body["ai"] = _ai(start, end)
    return body


# ---- what is behind a card or a mark ----


def _companies_in_state(state):
    return [subscription.company_id for subscription, found in _subscriptions() if found == state]


def _company_items(ids, limit):
    companies = list(Company.objects.filter(pk__in=ids).order_by("name")[:limit])
    return _company_rows(companies)


def _call_item(call):
    return {
        "type": "ai_call",
        "id": str(call.pk),
        "company_id": str(call.company_id),
        "model": call.model,
        "purpose": call.purpose,
        "result": call.result,
        "failure": call.failure,
        "tokens": call.tokens_in + call.tokens_out,
        "cost": _money(call.estimated_cost),
        "at": call.created_at.isoformat(),
    }


def _job_item(job):
    return {
        "type": "job",
        "id": job["id"],
        "company_id": job["company_id"],
        "company": job["company"],
        "reason": job["reason"],
        "at": job["since"],
    }


def _request_item(item):
    return {
        "type": "data_request",
        "id": item["id"],
        "company_id": item["company_id"],
        "company": item["company"],
        "request_type": item["kind"],
        "status": item["status"],
        "due_on": item["due_on"].isoformat(),
        "overdue": item["overdue"],
    }


def detail(role, kind, key, raw_days):
    """{"total", "items"}: companies (or AI calls for admins who may see them) behind a card or
    a mark; at most `dashboard.detail_limit` items with the real total."""
    limit = get_setting("dashboard.detail_limit")
    days = checked_period(raw_days)
    start, _, end = windows(days)
    if kind == "metric" and key == "companies":
        ids = in_days(Company.objects.all(), "created_at", start, end).values_list("pk", flat=True)
        return {"total": len(ids), "items": _company_items(ids, limit)}
    if kind == "metric" and key == "cvs_scored":
        top = _top_companies(role, start, end)
        return {"total": len(top), "items": top[:limit]}
    if kind == "state" and key in STATES:
        ids = _companies_in_state(key)
        if key == "no_plan":
            have = Subscription.objects.values_list("company_id", flat=True)
            ids += list(Company.objects.exclude(pk__in=have).values_list("pk", flat=True))
        return {"total": len(ids), "items": _company_items(ids, limit)}
    if kind == "plan":
        try:
            plan = Plan.objects.get(pk=int(key))
        except (ValueError, Plan.DoesNotExist):
            raise Http404 from None
        require_action_for(role, "payment.view")
        ids = [
            subscription.company_id
            for subscription, _state in _paying(_subscriptions())
            if subscription.plan_id == plan.pk
        ]
        return {"total": len(ids), "items": _company_items(ids, limit)}
    if kind == "pending" and key in ("past_due", "grants_expiring", "suspended"):
        subscriptions = _subscriptions()
        horizon = timezone.now() + timedelta(
            days=get_setting("admin_dashboard.expiring_grant_days")
        )
        if key == "past_due":
            ids = [s.company_id for s, state in subscriptions if state == State.PAST_DUE]
        elif key == "grants_expiring":
            ids = [
                s.company_id
                for s, state in subscriptions
                if state == State.GRANTED_FREE and s.period_end and s.period_end <= horizon
            ]
        else:
            ids = list(
                Company.objects.filter(status=Company.Status.SUSPENDED).values_list("pk", flat=True)
            )
        return {"total": len(ids), "items": _company_items(ids, limit)}
    if kind == "pending" and key == "failed_ai_calls":
        require_action_for(role, "ai.view")
        calls = _failed_calls(timezone.now()).order_by("-created_at")
        return {"total": calls.count(), "items": [_call_item(call) for call in calls[:limit]]}
    if kind == "pending" and key == "failed_jobs":
        require_action_for(role, "job.view")
        jobs = job_monitor.list_jobs(state=job_monitor.FAILED)
        return {
            "total": jobs["total"],
            "items": [_job_item(job) for job in jobs["items"][:limit]],
        }
    if kind == "pending" and key == "data_requests":
        require_action_for(role, "data_request.handle")
        waiting = data_requests.attention_items(limit)
        return {"total": waiting["total"], "items": [_request_item(i) for i in waiting["items"]]}
    if kind in ("ai_purpose", "ai_model") and key:
        require_action_for(role, "ai.view")
        column = "purpose" if kind == "ai_purpose" else "model"
        calls = in_days(AiCall.objects.filter(**{column: key}), "created_at", start, end).order_by(
            "-created_at"
        )
        return {"total": calls.count(), "items": [_call_item(call) for call in calls[:limit]]}
    raise form_error({"kind": "Choose something that can be opened."})


def require_action_for(role, action):
    """The same refusal as any other route when this role may not do `action`."""
    require_role(_Actor(role), roles_allowed(action))


class _Actor:
    """What `require_role` needs of a user: the role."""

    def __init__(self, role):
        self.role = role


# ---- the report ----


def report(role, raw_days):
    days = checked_period(raw_days)
    start, before, end = windows(days)
    cards = _cards(role, start, before, end)
    names = {
        "companies": "New companies",
        "cvs_scored": "CVs scored",
        "ai_cost": "AI cost (USD)",
    }
    subscriptions = _subscriptions()
    body = {
        "days": days,
        "generated_on": timezone.now().date().isoformat(),
        "summary": [
            {
                "metric": names[name],
                "current": found["value"],
                "previous": found["previous"],
                "change": found["change"],
            }
            for name, found in cards.items()
        ],
        "companies": [
            {
                "company": row["name"],
                "plan": row["plan"],
                "state": row["state"],
                "cvs_scored": row["cvs_scored"],
                **({"cost": row["cost"]} if "cost" in row else {}),
            }
            for row in _top_companies(role, start, end)
        ],
    }
    if _can(role, "payment.view"):
        revenue = _revenue(subscriptions)
        body["revenue"] = {
            "mrr": revenue["mrr"],
            "ai_cost": revenue["ai_cost"],
            "margin_percent": revenue["margin_percent"],
            "plans": [
                {"plan": row["name"], "subscribers": row["subscribers"], "mrr": row["mrr"]}
                for row in revenue["plans"]
            ],
        }
    return body


def _safe(cell):
    text = "" if cell is None else str(cell)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def report_csv(body):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["Report for the last", f"{body['days']} days", "Created", body["generated_on"]]
    )
    writer.writerow([])
    writer.writerow(["Metric", "This period", "Previous period", "Change"])
    for row in body["summary"]:
        writer.writerow([_safe(row[key]) for key in ("metric", "current", "previous", "change")])
    if "revenue" in body:
        writer.writerow([])
        writer.writerow(["Estimated monthly revenue (USD)", body["revenue"]["mrr"]])
        writer.writerow(["AI cost, last month (USD)", body["revenue"]["ai_cost"]])
        writer.writerow(["Margin (%)", _safe(body["revenue"]["margin_percent"])])
        writer.writerow([])
        writer.writerow(["Plan", "Subscribers", "Monthly revenue (USD)"])
        for row in body["revenue"]["plans"]:
            writer.writerow([_safe(row["plan"]), row["subscribers"], row["mrr"]])
    writer.writerow([])
    columns = ["Company", "Plan", "Subscription", "CVs scored"]
    with_cost = any("cost" in row for row in body["companies"])
    writer.writerow([*columns, *(["AI cost (USD)"] if with_cost else [])])
    for row in body["companies"]:
        cells = [row["company"], row["plan"], row["state"], row["cvs_scored"]]
        if with_cost:
            cells.append(row.get("cost"))
        writer.writerow([_safe(cell) for cell in cells])
    return out.getvalue()
