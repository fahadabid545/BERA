"""What a company's plan allows, and whether one more thing fits. The checks only answer (allowed
or not, why, and which prompt to show); the tickets that create projects, take uploads and run
AI call them and refuse in the server, so the screen is never the only guard.

Limits are always read fresh through `limit_for`, so a changed plan or an admin's override takes
effect immediately. A caller that accepts files must hold the company's row lock while it checks
and then records them (see `usage.service`), so parallel uploads cannot pass a limit together.
"""

import sys
from dataclasses import dataclass

from core.errors import AppError
from freeaccess import entitlement
from freeaccess.models import FreeAccess
from platform_settings.service import get_setting
from usage import service as usage

from . import trials
from .models import LimitOverride, Plan
from .subscriptions import State, access_of, get_subscription

UPGRADE = "upgrade"
RENEWAL = "renewal"
HIGHEST_PLAN = "highest_plan"  # a limit is reached and no bigger plan exists
# A plan may leave a limit empty (None): nothing is capped. Callers compare and slice by `room`,
# so an unlimited limit leaves "room" for any number of items.
UNLIMITED_ROOM = sys.maxsize

CVS_PER_MONTH = "cvs_per_month"
CVS_PER_PROJECT = "cvs_per_project"
MAX_PROJECTS = "max_projects"
MAX_TOP_N = "max_top_n"
MAX_TEAM_ACCOUNTS = "max_team_accounts"
LIMIT_NAMES = (
    CVS_PER_MONTH,
    CVS_PER_PROJECT,
    MAX_PROJECTS,
    MAX_TOP_N,
    MAX_TEAM_ACCOUNTS,
)

CODES = {
    CVS_PER_MONTH: "monthly_cv_limit_reached",
    CVS_PER_PROJECT: "project_cv_limit_reached",
    MAX_PROJECTS: "project_limit_reached",
    MAX_TOP_N: "top_n_limit_exceeded",
    MAX_TEAM_ACCOUNTS: "team_limit_reached",
}
MESSAGES = {
    CVS_PER_MONTH: "You have reached your plan's limit of {limit} CVs this month.",
    CVS_PER_PROJECT: "This project has reached your plan's limit of {limit} CVs.",
    MAX_PROJECTS: "You have reached your plan's limit of {limit} projects.",
    MAX_TOP_N: "Your plan allows a top list of at most {limit}.",
    MAX_TEAM_ACCOUNTS: "Your company can have at most {limit} accounts, including the owner. "
    "Remove someone or revoke an invitation first.",
}
EXPIRED_CODE = "subscription_expired"
EXPIRED_MESSAGE = "Your subscription has ended, so this is not available. Renew to continue."


@dataclass(frozen=True)
class LimitCheck:
    allowed: bool
    limit_name: str
    code: str = ""
    message: str = ""
    prompt: str | None = (
        None  # "upgrade", "renewal" or "highest_plan": what the screen should offer
    )
    limit: int | None = None
    used: int = 0
    room: int = 0  # how many more fit

    def raise_if_blocked(self):
        if not self.allowed:
            raise AppError(
                self.code,
                self.message,
                status_code=409,
                details={"limit": self.limit, "prompt": self.prompt},
            )


def limit_for(company_id, name):
    """The company's limit: its own override, else its plan's value. A company with no plan has
    none (0), except team size, which keeps the platform default until a plan is chosen."""
    if name not in LIMIT_NAMES:
        raise KeyError(name)
    override = LimitOverride.objects.filter(company_id=company_id, name=name).first()
    if override:
        return override.value
    access = access_of(company_id)
    if access.grant is not None and access.grant.kind == FreeAccess.Kind.BETA:
        return entitlement.beta_limit(name)
    if access.plan is not None:
        return getattr(access.plan, name)
    return get_setting("team.max_accounts_per_company") if name == MAX_TEAM_ACCOUNTS else 0


def is_on_highest_plan(company_id):
    """No other active plan costs more than the company's own."""
    plan = access_of(company_id).plan
    if plan is None or plan.price_usd is None:
        return False
    dearer = Plan.objects.filter(status=Plan.Status.ACTIVE, price_usd__gt=plan.price_usd)
    return not dearer.exists()


def prompt_kind(company_id):
    """Renewal for an expired subscription; for the highest plan (nothing bigger to upgrade to)
    the highest-plan prompt, which offers contact instead; Upgrade otherwise."""
    subscription = get_subscription(company_id)
    if access_of(company_id).state == State.EXPIRED:
        # A company whose only subscription was a free trial has nothing to renew: it chooses.
        never_paid = (
            subscription.trial_started_at is not None and not subscription.stripe_subscription_id
        )
        return UPGRADE if never_paid else RENEWAL
    if trials.on_trial(subscription):
        return UPGRADE  # a trial is not a plan to upgrade from, even on the highest plan
    return HIGHEST_PLAN if is_on_highest_plan(company_id) else UPGRADE


def _expired(company_id, name):
    if access_of(company_id).state != State.EXPIRED:
        return None
    return LimitCheck(
        False,
        name,
        code=EXPIRED_CODE,
        message=EXPIRED_MESSAGE,
        prompt=prompt_kind(company_id),
        limit=limit_for(company_id, name),
    )


def _count_check(company_id, name, used, requested):
    """Allowed when `requested` more fit under the limit."""
    if blocked := _expired(company_id, name):
        return blocked
    limit = limit_for(company_id, name)
    if limit is None:
        return LimitCheck(True, name, limit=None, used=used, room=UNLIMITED_ROOM)
    room = max(limit - used, 0)
    if requested > room:
        return LimitCheck(
            False,
            name,
            code=CODES[name],
            message=MESSAGES[name].format(limit=limit),
            prompt=prompt_kind(company_id),
            limit=limit,
            used=used,
            room=room,
        )
    return LimitCheck(True, name, limit=limit, used=used, room=room)


def _trial_check(subscription, requested):
    """The CV limit of a running free trial, counted over the whole trial."""
    limit, used = subscription.trial_cv_limit, trials.cvs_used(subscription)
    room = max(limit - used, 0)
    if requested > room:
        return LimitCheck(
            False,
            CVS_PER_MONTH,
            code=trials.TRIAL_CV_LIMIT_CODE,
            message=trials.TRIAL_CV_LIMIT_MESSAGE.format(limit=limit),
            prompt=prompt_kind(subscription.company_id),
            limit=limit,
            used=used,
            room=room,
        )
    return LimitCheck(True, CVS_PER_MONTH, limit=limit, used=used, room=room)


BETA_DAILY_CODE = "beta_daily_cv_limit_reached"
BETA_DAILY_MESSAGE = "Your beta access allows {limit} CVs a day. Try again tomorrow."


def _beta_daily_check(company_id, requested):
    """Beta access's CVs a day, counted from the start of today (the server's day)."""
    limit = get_setting("beta.cvs_per_day")
    used = usage.cvs_since(company_id, entitlement.start_of_today())
    room = max(limit - used, 0)
    if requested > room:
        return LimitCheck(
            False,
            CVS_PER_MONTH,
            code=BETA_DAILY_CODE,
            message=BETA_DAILY_MESSAGE.format(limit=limit),
            prompt=None,
            limit=limit,
            used=used,
            room=room,
        )
    return LimitCheck(True, CVS_PER_MONTH, limit=limit, used=used, room=room)


def check_cvs_this_month(company_id, requested=1):
    """CVs scored this period plus those accepted and still waiting. A CV that failed has given
    its allowance back, because only scored and waiting ones are counted. A running free trial
    also has its own limit over the whole trial; the stricter of the two answers."""
    used = usage.current_usage(company_id)["cvs_scored"] + usage.waiting_cvs(company_id)
    monthly = _count_check(company_id, CVS_PER_MONTH, used, requested)
    subscription = get_subscription(company_id)
    checks = [monthly]
    if trials.on_trial(subscription):
        checks.append(_trial_check(subscription, requested))
    grant = access_of(company_id).grant
    if grant is not None and grant.kind == FreeAccess.Kind.BETA:
        checks.append(_beta_daily_check(company_id, requested))
    return min(checks, key=lambda check: check.room)


def check_cvs_per_project(company_id, cvs_in_project, requested=1):
    return _count_check(company_id, CVS_PER_PROJECT, cvs_in_project, requested)


def check_projects(company_id, projects_now, requested=1):
    return _count_check(company_id, MAX_PROJECTS, projects_now, requested)


def check_team_size(company_id, seats_in_use, requested=1):
    """`seats_in_use` is the people of the company plus open invitations."""
    return _count_check(company_id, MAX_TEAM_ACCOUNTS, seats_in_use, requested)


def check_top_n(company_id, top_n):
    """A top list of `top_n` is allowed up to the limit."""
    check = _count_check(company_id, MAX_TOP_N, 0, top_n)
    return LimitCheck(**{**check.__dict__, "used": top_n}) if not check.allowed else check


def check_ai_allowed(company_id):
    """AI work needs a running plan, trial or free access. There is no token limit: companies are
    bound by their projects and CVs only."""
    if blocked := _expired(company_id, CVS_PER_MONTH):
        return blocked
    return LimitCheck(True, CVS_PER_MONTH)


@dataclass(frozen=True)
class SkippedFile:
    file: object
    code: str
    message: str
    prompt: str | None


@dataclass(frozen=True)
class BatchSplit:
    accepted: list
    skipped: list


def split_batch(company_id, files, cvs_in_project):
    """Accepts files in order up to what is left of the month and of the project; every other
    file is returned with exactly why it was skipped (the limit that ran out first)."""
    asked = len(files)
    blocking = [
        check
        for check in (
            check_cvs_this_month(company_id, asked),
            check_cvs_per_project(company_id, cvs_in_project, asked),
        )
        if not check.allowed
    ]
    if not blocking:
        return BatchSplit(accepted=list(files), skipped=[])
    reason = min(blocking, key=lambda check: check.room)
    return BatchSplit(
        accepted=list(files[: reason.room]),
        skipped=[
            SkippedFile(file, reason.code, reason.message, reason.prompt)
            for file in files[reason.room :]
        ],
    )
