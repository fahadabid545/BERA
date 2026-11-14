"""Recommendation and insights: a plain label, and a few things to look at, for each candidate.

The label comes from the final score: Strong match at or above the project's threshold (its
recommendation threshold, which starts at the platform's strong-match limit), Possible at or above
the platform's possible-match limit, otherwise Not recommended. A score within a few points of
either limit (`recommendation.borderline_points`) is also marked Borderline, because the label could
easily have gone the other way.

Strengths (met requirements), risks (missing or partly met ones) and interview questions are made
by fixed rules from the requirement results and the platform's question templates, so they are the
same every time and cost no AI call. The heaviest requirements come first, must-haves before
nice-to-haves. They quote only the requirement wording, never the CV. The label is a guide: the
note saying so is stored with it, and the recruiter decides.
"""

from platform_settings.service import get_setting
from projects.models import Requirement

STRONG, POSSIBLE, NOT_RECOMMENDED = "strong_match", "possible", "not_recommended"
LABELS = (STRONG, POSSIBLE, NOT_RECOMMENDED)
MET, PARTLY_MET, MISSING = "met", "partly_met", "missing"
MUST = Requirement.Kind.MUST
# Missing before partly met when risks and questions are picked.
VERDICT_ORDER = {MISSING: 0, PARTLY_MET: 1, MET: 2}
QUESTION_SETTING = {
    MISSING: "recommendation.question_missing",
    PARTLY_MET: "recommendation.question_partly_met",
    MET: "recommendation.question_met",
}


def label_for(score, threshold):
    """The label for a score, given the project's strong-match threshold."""
    if score >= threshold:
        return STRONG
    if score >= get_setting("scoring.possible_match_min"):
        return POSSIBLE
    return NOT_RECOMMENDED


def is_borderline(score, threshold):
    """True when the score is within the borderline distance of either limit."""
    distance = get_setting("recommendation.borderline_points")
    limits = (threshold, get_setting("scoring.possible_match_min"))
    return any(abs(score - limit) <= distance for limit in limits)


def _most_important_first(judged):
    """`judged` is (requirement, verdict). Must-haves first, then the heavier, then as ordered."""
    return sorted(
        judged, key=lambda item: (item[0].kind != MUST, -item[0].weight, item[0].position)
    )


def _item(requirement, verdict):
    return {"requirement": requirement.text, "kind": requirement.kind, "verdict": verdict}


def strengths(judged):
    met = [item for item in judged if item[1] == MET]
    ordered = _most_important_first(met)
    return [_item(*item) for item in ordered[: get_setting("recommendation.max_strengths")]]


def risks(judged):
    lacking = [item for item in judged if item[1] != MET]
    ordered = sorted(
        _most_important_first(lacking),
        key=lambda item: (item[0].kind != MUST, VERDICT_ORDER[item[1]]),
    )  # stable: inside a group the heavier one is still first
    return [_item(*item) for item in ordered[: get_setting("recommendation.max_risks")]]


def interview_questions(judged):
    """Gaps first (missing, then partly met, must-haves before nice-to-haves), then a check on
    what is met."""
    ordered = sorted(
        _most_important_first(judged),
        key=lambda item: (item[1] == MET, item[0].kind != MUST, VERDICT_ORDER[item[1]]),
    )
    questions = []
    for requirement, verdict in ordered[: get_setting("recommendation.max_questions")]:
        template = get_setting(QUESTION_SETTING[verdict])
        questions.append(template.replace("{requirement}", requirement.text))
    return questions


def recommend(score, threshold, judged):
    """The stored recommendation fields for a score and its judged requirements."""
    return {
        "label": label_for(score, threshold),
        "borderline": is_borderline(score, threshold),
        "strengths": strengths(judged),
        "risks": risks(judged),
        "interview_questions": interview_questions(judged),
        "guide_note": get_setting("recommendation.guide_note"),
    }
