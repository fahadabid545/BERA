"""The AI playground: a super admin tries the reading and scoring on one CV and one job
description, with the models and prompt versions of their choice, and sees everything.

A test run reads the CV, proposes the requirements from the job description, judges the CV against
them and works out the score with the platform's own rules, using the same functions as real
processing. It is done in memory: nothing is saved to any company, project, candidate or CV, and
the uploaded file and its text are thrown away when the answer is sent. The only thing written is
the `AiCall` record of each call (ids, numbers and the purpose, never text), which has no company.

Test runs are paid from their own budget (`ai.playground_monthly_budget_usd`, US dollars per UTC
month), counted from those records. One run at a time: a run holds a database lock from its first
check to its last call, so two runs at the same moment can never both pass the check and go over
the budget. The budget is checked before every AI call, so a run stops once it is used up; the
last call can overshoot by what that one call costs, which is only known afterwards.
"""

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone
from psycopg import sql

from audit.service import record
from core.errors import AppError, form_error
from cvs.evaluation import judge_texts
from cvs.fairness import remove_personal_details
from cvs.file_checks import check_cv_file, check_name_and_size
from cvs.processing import PermanentFailure
from cvs.profile_reading import request_profile
from cvs.recommendation import recommend
from cvs.scoring import combine
from cvs.text_reading import CvTextUnreadable, read_text
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting
from projects.extraction import request_requirements
from projects.models import Requirement
from projects.scoring_settings import scoring_defaults

from . import prompt_versions, spend_alerts
from .client import AiPaused, AiUnavailable, call_ai
from .models import AiCall, AiModel, AiSpendAlert

logger = logging.getLogger(__name__)

PURPOSE = AiCall.Purpose.PLAYGROUND
BUDGET_SETTING = "ai.playground_monthly_budget_usd"
MONEY_PLACES = Decimal("0.000001")
# The number of the database lock that lets one test run happen at a time.
RUN_LOCK_NUMBER = 1_550_155

BUDGET_USED_UP = "The test budget for this month is used up."
BUSY_MESSAGE = "Another test run is in progress. Try again in a moment."
AI_UNAVAILABLE_MESSAGE = "The AI could not answer. Try again later."
NO_SUCH_VERSION = "There is no such version."
NOT_SWITCHED_ON = "Choose a model that is switched on."
NO_REQUIREMENTS = "No requirements could be found in this job description."
REQUIREMENTS_STEP, READING_STEP, SCORING_STEP = "requirement_extraction", "reading", "scoring"
STEPS = (READING_STEP, REQUIREMENTS_STEP, SCORING_STEP)


@dataclass
class _Usage:
    """Tokens and cost of one step of a run, from the answers the AI gave."""

    tokens_in: int = 0
    tokens_out: int = 0
    cost: Decimal = Decimal(0)


@dataclass
class _Tally:
    steps: dict = field(default_factory=lambda: {step: _Usage() for step in STEPS})
    current: str = READING_STEP

    def add(self, answer):
        usage = self.steps[self.current]
        usage.tokens_in += answer.tokens_in
        usage.tokens_out += answer.tokens_out
        usage.cost += answer.estimated_cost

    def describe(self):
        steps = [
            {
                "step": step,
                "tokens_in": usage.tokens_in,
                "tokens_out": usage.tokens_out,
                "cost": _money(usage.cost),
            }
            for step, usage in self.steps.items()
        ]
        return {
            "steps": steps,
            "tokens_in": sum(usage.tokens_in for usage in self.steps.values()),
            "tokens_out": sum(usage.tokens_out for usage in self.steps.values()),
            "cost": _money(sum(usage.cost for usage in self.steps.values())),
        }


def _money(value):
    return str(Decimal(value).quantize(MONEY_PLACES))


def budget(now=None):
    """The month's test budget: the limit, what was spent and what is left (never below 0)."""
    label, start = spend_alerts.period_of(AiSpendAlert.Kind.MONTHLY, now or timezone.now())
    limit = Decimal(str(get_setting(BUDGET_SETTING)))
    spent = spend_alerts.spent_since(start, purpose=PURPOSE)
    return {
        "month": label,
        "limit": _money(limit),
        "spent": _money(spent),
        "remaining": _money(max(Decimal(0), limit - spent)),
        "used_up": spent >= limit,
    }


def options():
    """What the page offers: the models that are switched on, the prompt versions and the budget."""
    versions = prompt_versions.overview()
    return {
        "models": [model.name for model in AiModel.objects.filter(enabled=True)],
        "prompts": {
            kind: [{"number": item["number"], "current": item["current"]} for item in items]
            for kind, items in versions.items()
            if kind in prompt_versions.PINNED_KINDS
        },
        "budget": budget(),
    }


def set_budget(amount, *, by, reason):
    """Sets the monthly test budget in US dollars; audited with its reason."""
    with transaction.atomic():
        old = get_setting(BUDGET_SETTING)
        PlatformSetting.objects.update_or_create(
            key=BUDGET_SETTING, defaults={"value": float(amount)}
        )
        record(
            "admin.ai_playground_budget_changed",
            actor=by,
            reason=reason,
            changes={"monthly_budget": {"old": str(old), "new": str(amount)}},
        )
    return budget()


def _lock_statement(function):
    """The lock call for the run lock, built with the driver's own quoting (never joined text)."""
    return sql.SQL("SELECT {}({})").format(sql.SQL(function), sql.Literal(RUN_LOCK_NUMBER))


@contextmanager
def _one_run_at_a_time():
    """Holds the database lock for the whole run; a second run is refused, not queued. The lock
    belongs to the connection, so it is let go if the server stops."""
    with connection.cursor() as cursor:
        cursor.execute(_lock_statement("pg_try_advisory_lock"))
        if not cursor.fetchone()[0]:
            raise AppError("playground_busy", BUSY_MESSAGE, status_code=409)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(_lock_statement("pg_advisory_unlock"))


def _check_budget():
    current = budget()
    if current["used_up"]:
        raise AppError(
            "playground_budget_used_up", BUDGET_USED_UP, status_code=409, details=current
        )


def _counting_ask(tally):
    """`call_ai` with the budget checked first and the answer counted, for one run."""

    def ask(company_id, **call):
        _check_budget()
        answer = call_ai(company_id, **call)
        tally.add(answer)
        return answer

    return ask


def _checked_choices(values):
    """The field errors of the choices: models that are switched on, prompt versions that exist."""
    problems = {}
    for field_name in ("reading_model", "scoring_model"):
        if not AiModel.objects.filter(name=values[field_name], enabled=True).exists():
            problems[field_name] = NOT_SWITCHED_ON
    for kind in prompt_versions.PINNED_KINDS:
        name = f"{kind}_prompt_version"
        if not prompt_versions.exists(kind, values[name]):
            problems[name] = NO_SUCH_VERSION
    if problems:
        raise form_error(problems)


def _read_cv_text(name, data):
    """The text of the uploaded CV, after the same file checks as a real upload, and a notice."""
    if problem := check_name_and_size(name, len(data)):
        raise form_error({"cv_file": problem.message})
    checked = check_cv_file(name, data)
    if checked.problem:
        raise form_error({"cv_file": checked.problem.message})
    try:
        return read_text(checked.file_type, data).text, checked.notice
    except CvTextUnreadable as error:
        raise form_error({"cv_file": error.message}) from error


def _score(proposed, judged):
    """The score, grade and recommendation from the judgements, by the platform's default
    scoring settings. The requirements are not saved, so they are plain unsaved objects."""
    settings = scoring_defaults()
    weight = get_setting("requirements.weight_default")
    requirements = [
        Requirement(position=number, kind=item["kind"], text=item["text"], weight=weight)
        for number, item in enumerate(proposed, 1)
    ]
    verdicts = [
        (requirement, judged[number].verdict) for number, requirement in enumerate(requirements, 1)
    ]
    outcome = combine(
        [(requirement.kind, requirement.weight, verdict) for requirement, verdict in verdicts],
        Decimal(settings["must_weight_percent"]),
        Decimal(settings["nice_weight_percent"]),
        settings["cap_on_missing_must_have"],
    )
    results = [
        {
            "kind": requirement.kind,
            "text": requirement.text,
            "weight": requirement.weight,
            "verdict": judged[number].verdict,
            "evidence": judged[number].evidence,
            "confidence": judged[number].confidence,
        }
        for number, requirement in enumerate(requirements, 1)
    ]
    score = {
        "score": str(outcome.score),
        "grade": outcome.grade,
        "must_score": None if outcome.must_score is None else str(outcome.must_score),
        "nice_score": None if outcome.nice_score is None else str(outcome.nice_score),
        "capped": outcome.capped,
        **recommend(outcome.score, settings["recommendation_threshold"], verdicts),
    }
    return results, score


def _stopped(error):
    """The shared error for a failure of the AI itself."""
    if isinstance(error, AiPaused):
        return AppError("ai_paused", str(error), status_code=503)
    if isinstance(error, PermanentFailure):
        return AppError("playground_unusable_answer", str(error), status_code=422)
    return AppError("ai_unavailable", AI_UNAVAILABLE_MESSAGE, status_code=503)


def run(
    *,
    file_name,
    file_bytes,
    job_description,
    reading_model,
    scoring_model,
    reading_prompt_version,
    scoring_prompt_version,
):
    """One test run, start to finish, with nothing saved to any company."""
    choices = {
        "reading_model": reading_model,
        "scoring_model": scoring_model,
        "reading_prompt_version": reading_prompt_version,
        "scoring_prompt_version": scoring_prompt_version,
    }
    _checked_choices(choices)
    cv_text, notice = _read_cv_text(file_name, file_bytes)
    with _one_run_at_a_time():
        _check_budget()
        tally = _Tally()
        ask = _counting_ask(tally)
        try:
            tally.current = READING_STEP
            profile, contact = request_profile(
                cv_text,
                company_id=None,
                purpose=PURPOSE,
                model=reading_model,
                prompt_version=reading_prompt_version,
                ask=ask,
            )
            # Scoring reads the CV without personal details, as real processing does.
            scoring_text = remove_personal_details(cv_text, contact)
            tally.current = REQUIREMENTS_STEP
            proposed = request_requirements(
                job_description,
                company_id=None,
                model=reading_model,
                purpose=PURPOSE,
                ask=ask,
            )
            if proposed is None:
                raise AppError("playground_no_requirements", NO_REQUIREMENTS, status_code=422)
            requirements = proposed[1][: get_setting("requirements.max_total")]
            tally.current = SCORING_STEP
            judged = judge_texts(
                scoring_text,
                {number: item["text"] for number, item in enumerate(requirements, 1)},
                company_id=None,
                purpose=PURPOSE,
                model=scoring_model,
                prompt_version=scoring_prompt_version,
                ask=ask,
            )
        except (AiUnavailable, PermanentFailure) as error:
            raise _stopped(error) from error
        results, score = _score(requirements, judged)
        return {
            "profile": profile,
            "requirements": results,
            "score": score,
            "usage": tally.describe(),
            "budget": budget(),
            "notice": notice,
        }
