"""The extra scoring factors: optional pictures of a candidate beside the requirements.

Seven factors, each worked out without AI from the saved profile (and the CV text and the AI's
confidence for two of them): experience years, education, seniority fit, recency of relevant
work, career gaps and job changes, CV readability and confidence. Each is a whole number from 0
to 100, or `None` for "Not found". Missing information is never turned into zero: a factor that
cannot be judged says why in its explanation.

Gaps and frequent job changes are shown with an explanation and only ever move a number a
project may weight; nothing here rejects, hides or excludes a candidate. Every factor is stored
whether it is switched on or not, so switching one on needs no recalculation. Which are on and how
much each counts is the project's choice (`projects/factor_settings.py`); combining them into the
final score is the Score calculation ticket.
"""

import hashlib
import json
import re
from datetime import date

from platform_settings.service import get_setting
from projects.factor_settings import EDUCATION_LEVELS, FACTORS, effective_factors

from .ats import job_keywords, readability_part
from .models import Candidate, ExtraFactorValues, RequirementResult
from .processing import StepContext, register_step
from .profile_checks import MONTHS_IN_YEAR, PRESENT, month_number

RULES_VERSION = 1
NOT_FOUND = "Not found"
PERCENT = 100
SENIORITY_ORDER = ("junior", "mid", "senior", "lead")
WORD = re.compile(r"[a-z]+")
JOB_FIELDS = ("required_years", "required_education", "seniority")


def _result(value, explanation):
    return {
        "value": None if value is None else max(0, min(PERCENT, round(value))),
        "explanation": explanation,
    }


def _not_found(why):
    return _result(None, f"{NOT_FOUND}. {why}")


def _month_now(today):
    return today.year * MONTHS_IN_YEAR + today.month - 1


def _job_months(job, today):
    """(start, end) month numbers of a job, or None when its start is unknown. A job that is
    current or has no end runs to today."""
    if not job.get("start"):
        return None
    start = month_number(job["start"], end=False)
    ending = job.get("end")
    stop = _month_now(today) if ending in (PRESENT, None) else month_number(ending, end=True)
    return start, max(start, stop)


# --- the seven factors --------------------------------------------------------------------


def experience_years(profile, config, **_):
    needed, years = config["required_years"], profile.get("years_of_experience")
    if needed is None:
        return _not_found("The job does not say how many years of experience it needs.")
    if years is None:
        return _not_found("The CV does not show how many years of experience there are.")
    if needed == 0:
        return _result(PERCENT, f"{years} years of experience found; none are required.")
    return _result(
        PERCENT * years / needed, f"{years} years of experience found, {needed} required."
    )


def _degree_level(profile):
    """The highest education level named in the profile's degrees, or None."""
    wanted = {level: set(get_setting(f"factors.{level}_words")) for level in EDUCATION_LEVELS}
    highest = None
    for entry in profile.get("education", []):
        words = set(WORD.findall(entry.get("degree", "").lower().replace(".", "")))
        for rank, level in enumerate(EDUCATION_LEVELS, 1):
            if words & wanted[level]:
                highest = max(highest or 0, rank)
    return highest


def education(profile, config, **_):
    needed = config["required_education"]
    if needed is None:
        return _not_found("The job does not say what education it needs.")
    level = _degree_level(profile)
    if level is None:
        return _not_found("The CV does not show an education level.")
    required = EDUCATION_LEVELS.index(needed) + 1
    name = EDUCATION_LEVELS[level - 1]
    if level >= required:
        return _result(PERCENT, f"A {name} degree found; {needed} required.")
    return _result(PERCENT * level / required, f"A {name} degree found, {needed} required.")


def _title_level(title):
    words = set(WORD.findall(title.lower()))
    for level in ("lead", "senior", "junior"):
        if words & set(get_setting(f"factors.{level}_words")):
            return level
    return "mid"


def seniority(profile, config, today, **_):
    wanted = config["seniority"]
    if wanted is None:
        return _not_found("The job does not say what seniority it needs.")
    dated = [(_job_months(job, today), job) for job in profile.get("jobs", [])]
    dated = [(months, job) for months, job in dated if months]
    if not dated:
        return _not_found("The CV shows no dated job title to judge seniority from.")
    latest = max(dated, key=lambda item: item[0])[1]
    level = _title_level(latest["title"])
    steps = abs(SENIORITY_ORDER.index(level) - SENIORITY_ORDER.index(wanted))
    value = PERCENT - steps * get_setting("factors.seniority_step_penalty")
    return _result(value, f"The latest job title reads as {level}; the job needs {wanted}.")


def recency(profile, config, today, job_description, **_):
    keywords = set(job_keywords(job_description))
    relevant = []
    for job in profile.get("jobs", []):
        months = _job_months(job, today)
        title_words = {
            word.rstrip("s") if len(word) > 3 else word
            for word in WORD.findall(job["title"].lower())
        }
        if months and title_words & keywords:
            relevant.append(months[1])
    if not relevant:
        return _not_found(
            "No dated job title matches the job description, so relevant work cannot be dated."
        )
    ago = max(0, _month_now(today) - max(relevant))
    if ago == 0:
        return _result(PERCENT, "Relevant work is current.")
    value = PERCENT - PERCENT * ago / get_setting("factors.recency_decay_months")
    return _result(value, f"The latest relevant work ended {ago} months ago.")


def gaps_and_changes(profile, config, today, **_):
    spans = sorted(m for m in (_job_months(job, today) for job in profile.get("jobs", [])) if m)
    if len(spans) < 2:
        return _not_found(
            "The CV shows fewer than two dated jobs, so gaps and changes cannot be seen."
        )
    minimum = get_setting("factors.gap_months")
    gaps, previous_end = [], spans[0][1]
    for start, stop in spans[1:]:
        if start - previous_end - 1 >= minimum:
            gaps.append(start - previous_end - 1)
        previous_end = max(previous_end, stop)
    window_start = _month_now(today) - get_setting("factors.changes_window_years") * MONTHS_IN_YEAR
    short = sum(
        stop - start + 1 < get_setting("factors.short_stint_months")
        for start, stop in spans
        if start >= window_start
    )
    frequent = short >= get_setting("factors.short_stints_flagged")
    value = PERCENT - get_setting("factors.gap_penalty") * len(gaps)
    value -= get_setting("factors.change_penalty") if frequent else 0
    notes = [f"{len(gaps)} gap(s) of {minimum} months or more" if gaps else "No gaps found"]
    notes.append(
        f"{short} short jobs in the last {get_setting('factors.changes_window_years')} years"
    )
    return _result(
        value,
        "; ".join(notes)
        + ". Gaps and job changes have many valid reasons and never reject a candidate.",
    )


def readability(profile, config, text, **_):
    if not (text or "").strip():
        return _not_found("There is no text to judge.")
    score, _lost = readability_part(text)
    return _result(score, "How easily the text of the CV can be read by a system.")


def confidence(profile, config, candidate, **_):
    levels = list(
        RequirementResult.objects.filter(candidate=candidate).values_list("confidence", flat=True)
    )
    if not levels:
        return _not_found("The CV has not been judged against the requirements yet.")
    worth = {
        "high": get_setting("factors.confidence_high"),
        "medium": get_setting("factors.confidence_medium"),
        "low": get_setting("factors.confidence_low"),
    }
    return _result(
        sum(worth[level] for level in levels) / len(levels),
        "How sure the AI was, on average, across the requirements.",
    )


CALCULATIONS = {
    "experience_years": experience_years,
    "education": education,
    "seniority": seniority,
    "recency": recency,
    "gaps_and_changes": gaps_and_changes,
    "readability": readability,
    "confidence": confidence,
}


# --- storing ------------------------------------------------------------------------------


def _basis(project, config):
    """What the stored values depend on besides the CV: the job's expectations and description."""
    wanted = {name: config[name] for name in JOB_FIELDS}
    wanted["description"] = project.job_description
    wanted["rules"] = RULES_VERSION
    return hashlib.sha256(json.dumps(wanted, sort_keys=True).encode()).hexdigest()


def calculate_factors(candidate, text=None, today=None):
    """The seven factor values of a candidate, as `{factor: {"value", "explanation"}}`. `text`
    is the CV text (the readability factor keeps its stored value when it is not given)."""
    project = candidate.project
    config = effective_factors(project)
    today = today or date.today()
    profile = candidate.profile.content
    stored = ExtraFactorValues.objects.filter(candidate=candidate).first()
    values = {}
    for name in FACTORS:
        if name == "readability" and text is None and stored:
            values[name] = stored.values[name]
            continue
        values[name] = CALCULATIONS[name](
            profile,
            config,
            candidate=candidate,
            text=text,
            today=today,
            job_description=project.job_description,
        )
    return values


def store_factors(candidate, text=None, today=None):
    project = candidate.project
    values = calculate_factors(candidate, text, today)
    saved, _ = ExtraFactorValues.objects.update_or_create(
        candidate=candidate,
        defaults={
            "company_id": candidate.company_id,
            "values": values,
            "basis_hash": _basis(project, effective_factors(project)),
        },
    )
    return saved


def refresh_project_factors(project):
    """After the job's expectations change: the stored values of the project's candidates are
    worked out again from their profiles (no AI, no CV text needed)."""
    for candidate in Candidate.objects.filter(project=project).select_related("profile"):
        store_factors(candidate)


def make_the_factors(context: StepContext):
    """Slot `extra_factors`: the factor values from the saved profile and the original text."""
    store_factors(context.cv_file.candidate, context.state["text"])


register_step("extra_factors", make_the_factors)
