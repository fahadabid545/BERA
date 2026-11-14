"""Score calculation: the final score, worked out by the system's own rules, never by the AI.

Each requirement counts by its verdict (met, partly met, missing: platform settings, 100, 50 and
0 points), weighted by the requirement's weight. Inside a group (must-have, nice-to-have) the
result is the weighted average of its requirements; the two groups are combined by the project's
split (default 70/30). If a project has only one group, that group alone gives the score, so a
perfect CV can still reach 100. The result is 0 to 100, rounded half up to one decimal, and the
grade comes from the rounded number (A, B, C, D, E; the limits are platform settings).

Optionally (per project) a missing must-have caps the score (60 by default).

The same results and settings always give the same score. Changing weights, the split or the cap
only recombines the stored results, so it never calls the AI (`recalculate_project`). Only the
requirements count: the ATS score and the extra factors are shown beside the score, not in it.
The recommendation (label, strengths, risks, questions) is made with the score; see
`recommendation.py`.
A candidate whose requirements have not all been judged (a requirement was added or edited) keeps
the score it has until the CV is judged again.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from platform_settings.service import get_setting
from projects.models import Requirement
from projects.scoring_settings import effective_settings

from .models import Candidate, CandidateScore, RequirementResult
from .processing import PermanentFailure, StepContext, register_step
from .recommendation import recommend

MUST, NICE = Requirement.Kind.MUST, Requirement.Kind.NICE
MET, PARTLY_MET, MISSING = (
    RequirementResult.Verdict.MET,
    RequirementResult.Verdict.PARTLY_MET,
    RequirementResult.Verdict.MISSING,
)
ONE_DECIMAL = Decimal("0.1")
PERCENT = Decimal(100)
GRADE_LIMITS = (
    ("A", "scoring.grade_a_min"),
    ("B", "scoring.grade_b_min"),
    ("C", "scoring.grade_c_min"),
    ("D", "scoring.grade_d_min"),
)
LOWEST_GRADE = "E"
NOT_JUDGED_REASON = "We could not score this CV. You can retry it."


@dataclass(frozen=True)
class Outcome:
    score: Decimal
    grade: str
    must_score: Decimal | None
    nice_score: Decimal | None
    capped: bool


def _points():
    return {
        MET: Decimal(get_setting("scoring.points_met")),
        PARTLY_MET: Decimal(get_setting("scoring.points_partly_met")),
        MISSING: Decimal(get_setting("scoring.points_missing")),
    }


def _rounded(value):
    return value.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def grade_for(score):
    """The grade a (rounded) score falls in."""
    for grade, setting in GRADE_LIMITS:
        if score >= get_setting(setting):
            return grade
    return LOWEST_GRADE


def _group_score(entries, points):
    """Weighted average of the points of `entries` (weight, verdict); None for an empty group."""
    total_weight = sum(weight for weight, _ in entries)
    if not total_weight:
        return None
    return sum(weight * points[verdict] for weight, verdict in entries) / total_weight


def combine(entries, must_percent, nice_percent, cap_missing_must_have):
    """The outcome for `entries`, a list of (kind, weight, verdict). None when there are none."""
    points = _points()
    must = _group_score([(w, v) for kind, w, v in entries if kind == MUST], points)
    nice = _group_score([(w, v) for kind, w, v in entries if kind == NICE], points)
    if must is None and nice is None:
        return None
    if nice is None:
        raw = must
    elif must is None:
        raw = nice
    else:
        raw = (must * must_percent + nice * nice_percent) / PERCENT
    raw = max(Decimal(0), min(PERCENT, raw))
    capped = False
    if cap_missing_must_have and any(k == MUST and v == MISSING for k, _, v in entries):
        cap = Decimal(get_setting("scoring.missing_must_have_cap"))
        capped = raw > cap
        raw = min(raw, cap)
    score = _rounded(raw)
    return Outcome(
        score,
        grade_for(score),
        None if must is None else _rounded(must),
        None if nice is None else _rounded(nice),
        capped,
    )


def _judged(candidate, requirements):
    """(requirement, verdict) for every requirement, or None when one has no current result
    (never judged, or judged against an older wording)."""
    results = {r.requirement_id: r for r in RequirementResult.objects.filter(candidate=candidate)}
    judged = []
    for requirement in requirements:
        result = results.get(requirement.pk)
        if result is None or result.requirement_text != requirement.text:
            return None
        judged.append((requirement, result.verdict))
    return judged


def score_candidate(candidate, requirements=None, settings=None):
    """Works out and stores the candidate's score from the stored results. Returns the stored
    `CandidateScore`, or None when the candidate cannot be scored now (nothing to score against,
    or a requirement not yet judged); an existing score is then left as it is."""
    if requirements is None:
        requirements = list(Requirement.objects.filter(project=candidate.project))
    judged = _judged(candidate, requirements)
    if not judged:
        return None
    entries = [(requirement.kind, requirement.weight, verdict) for requirement, verdict in judged]
    settings = settings or effective_settings(candidate.project)
    outcome = combine(
        entries,
        Decimal(settings["must_weight_percent"]),
        Decimal(settings["nice_weight_percent"]),
        settings["cap_on_missing_must_have"],
    )
    saved, _ = CandidateScore.objects.update_or_create(
        candidate=candidate,
        defaults={
            "company_id": candidate.company_id,
            "score": outcome.score,
            "grade": outcome.grade,
            "must_score": outcome.must_score,
            "nice_score": outcome.nice_score,
            "capped": outcome.capped,
            **recommend(outcome.score, settings["recommendation_threshold"], judged),
        },
    )
    return saved


def recalculate_project(project):
    """Scores every candidate of the project again from the stored results; no AI. Returns how
    many candidates' scores changed (a new score counts)."""
    requirements = list(Requirement.objects.filter(project=project))
    settings = effective_settings(project)
    changed = 0
    for candidate in Candidate.objects.filter(project=project):
        before = CandidateScore.objects.filter(candidate=candidate).first()
        before_values = before and (before.score, before.grade, before.capped, before.label)
        after = score_candidate(candidate, requirements, settings)
        if after and (after.score, after.grade, after.capped, after.label) != before_values:
            changed += 1
    return changed


def calculate_the_score(context: StepContext):
    """Slot `scoring`: the final score from the results the evaluation step saved."""
    if score_candidate(context.cv_file.candidate) is None:
        raise PermanentFailure(NOT_JUDGED_REASON)


register_step("scoring", calculate_the_score)
