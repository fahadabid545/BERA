"""What a company's plan allows, and whether one more thing fits. The checks only answer (allowed
or not, why, and which prompt to show); the tickets that create projects, take uploads and run
AI call them and refuse in the server, so the screen is never the only guard.

Limits are always read fresh through `limit_for`, so a changed plan or an admin's override takes
effect immediately. A caller that accepts files must hold the company's row lock while it checks
and then records them (see `usage.service`), so parallel uploads cannot pass a limit together.
"""

from dataclasses import dataclass

from core.errors import AppError
from platform_settings.service import get_setting
from usage import service as usage

from .models import LimitOverride, Plan
from .subscriptions import State, effective_state, get_subscription

UPGRADE = "upgrade"
RENEWAL = "renewal"

CVS_PER_MONTH = "cvs_per_month"
CVS_PER_PROJECT = "cvs_per_project"
MAX_PROJECTS = "max_projects"
MAX_TOP_N = "max_top_n"
MAX_TEAM_ACCOUNTS = "max_team_accounts"
MONTHLY_AI_TOKEN_CAP = "monthly_ai_token_cap"
LIMIT_NAMES = (
    CVS_PER_MONTH,
    CVS_PER_PROJECT,
    MAX_PROJECTS,
    MAX_TOP_N,
    MAX_TEAM_ACCOUNTS,
    MONTHLY_AI_TOKEN_CAP,
)

CODES = {
    CVS_PER_MONTH: "monthly_cv_limit_reached",
    CVS_PER_PROJECT: "project_cv_limit_reached",
    MAX_PROJECTS: "project_limit_reached",
    MAX_TOP_N: "top_n_limit_exceeded",
    MAX_TEAM_ACCOUNTS: "team_limit_reached",
    MONTHLY_AI_TOKEN_CAP: "ai_paused_token_cap",
}
MESSAGES = {
    CVS_PER_MONTH: "You have reached your plan's limit of {limit} CVs this month.",
    CVS_PER_PROJECT: "This project has reached your plan's limit of {limit} CVs.",
    MAX_PROJECTS: "You have reached your plan's limit of {limit} projects.",
    MAX_TOP_N: "Your plan allows a top list of at most {limit}.",
    MAX_TEAM_ACCOUNTS: "Your company can have at most {limit} accounts, including the owner. "
    "Remove someone or revoke an invitation first.",
    MONTHLY_AI_TOKEN_CAP: "Your company has used all its AI allowance for this period. AI work "
    "is paused until the next period or until the limit is raised.",
}
EXPIRED_CODE = "subscription_expired"
EXPIRED_MESSAGE = "Your subscription has ended, so this is not available. Renew to continue."


@dataclass(frozen=True)
class LimitCheck:
    allowed: bool
    limit_name: str
    code: str = ""
    message: str = ""
    prompt: str | None = None  # "upgrade" or "renewal", what the screen should offer
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
    plan = get_subscription(company_id).plan
    if plan is not None:
        return getattr(plan, name)
    return get_setting("team.max_accounts_per_company") if name == MAX_TEAM_ACCOUNTS else 0


def is_on_highest_plan(company_id):
    """No other active plan costs more than the company's own."""
    plan = get_subscription(company_id).plan
    if plan is None or plan.price_usd is None:
        return False
    dearer = Plan.objects.filter(status=Plan.Status.ACTIVE, price_usd__gt=plan.price_usd)
    return not dearer.exists()


def prompt_kind(company_id):
    """Renewal for an expired subscription or the highest plan (there is nothing bigger to
    upgrade to); Upgrade otherwise."""
    if effective_state(get_subscription(company_id)) == State.EXPIRED:
        return RENEWAL
    return RENEWAL if is_on_highest_plan(company_id) else UPGRADE


def _expired(company_id, name):
    if effective_state(get_subscription(company_id)) != State.EXPIRED:
        return None
    return LimitCheck(
        False,
        name,
        code=EXPIRED_CODE,
        message=EXPIRED_MESSAGE,
        prompt=RENEWAL,
        limit=limit_for(company_id, name),
    )


def _count_check(company_id, name, used, requested):
    """Allowed when `requested` more fit under the limit."""
    if blocked := _expired(company_id, name):
        return blocked
    limit = limit_for(company_id, name)
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


def check_cvs_this_month(company_id, requested=1):
    """CVs scored this period plus those accepted and still waiting. A CV that failed has given
    its allowance back, because only scored and waiting ones are counted."""
    used = usage.current_usage(company_id)["cvs_scored"] + usage.waiting_cvs(company_id)
    return _count_check(company_id, CVS_PER_MONTH, used, requested)


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
    """AI work is paused once the period's tokens (in and out) reach the cap, until the next
    period or a limit increase."""
    if blocked := _expired(company_id, MONTHLY_AI_TOKEN_CAP):
        return blocked
    current = usage.current_usage(company_id)
    used = current["tokens_in"] + current["tokens_out"]
    return _count_check(company_id, MONTHLY_AI_TOKEN_CAP, used, 1)


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
