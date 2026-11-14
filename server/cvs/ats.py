"""The ATS score: how well an applicant tracking system would read a CV. No AI is involved, so
the same input always gives the same result.

Four parts, each 0 to 100, are combined with the weights in the platform settings:

- keywords: how many of the job description's most frequent keywords the CV contains;
- sections: contact details, experience, education and skills are all present;
- readability: enough text but not too much, ordinary characters, and lines that hold words;
- formatting: no pages that are pictures of text, and not too many pages.

The result is a whole number from 0 to 100 and a short list of what lowered it, largest loss
first. Reasons are generic and name no personal detail; a missing keyword is the job
description's own word. The score is stored apart from the AI score (`AtsScore`) and is never
mixed into it.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from platform_settings.service import get_setting

from .ats_words import STOPWORDS
from .duplicates import EMAIL
from .fairness import PHONE

RULES_VERSION = 1  # change when the rules above change, so stored scores say which they used
TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")
PART_SCORE_MAX = 100
SECTIONS = (
    ("experience", "ats.experience_headings", "No experience section was found."),
    ("education", "ats.education_headings", "No education section was found."),
    ("skills", "ats.skills_headings", "No skills section was found."),
)
UNREADABLE_CATEGORIES = ("S", "C")  # symbols (icon fonts, emoji) and control or private characters
CHECKS_PER_SECTIONS_PART = 4  # contact, experience, education, skills
CHECKS_PER_READABILITY_PART = 4
CHECKS_PER_FORMATTING_PART = 2


@dataclass(frozen=True)
class Layout:
    """What the file itself shows. `image_pages` is how many pages are mostly a picture."""

    page_count: int | None = None
    image_pages: int = 0


@dataclass(frozen=True)
class Reason:
    code: str
    message: str
    points: float  # how much of the 100 this cost, after weighting


@dataclass(frozen=True)
class AtsResult:
    score: int
    reasons: list


def _normal(word):
    """A keyword as compared: no trailing full stop, and a plural 'services' matches 'service'."""
    word = word.rstrip(".")
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def tokens(text):
    return [_normal(token) for token in TOKEN.findall(unicodedata.normalize("NFKC", text).lower())]


def job_keywords(job_description):
    """The job description's most frequent meaningful words, most frequent first, ties in the
    order they first appear."""
    shortest = get_setting("ats.keyword_min_length")
    counted = Counter(
        token
        for token in tokens(job_description)
        if len(token) >= shortest and token not in STOPWORDS and not token.isdigit()
    )
    first_seen = {
        token: position for position, token in enumerate(dict.fromkeys(tokens(job_description)))
    }
    ranked = sorted(counted, key=lambda token: (-counted[token], first_seen[token]))
    return ranked[: get_setting("ats.keyword_count")]


def _keyword_part(text, job_description):
    keywords = job_keywords(job_description)
    if not keywords:
        return PART_SCORE_MAX, []  # nothing to miss
    present = set(tokens(text))
    missing = [word for word in keywords if word not in present]
    score = PART_SCORE_MAX * (len(keywords) - len(missing)) / len(keywords)
    if not missing:
        return score, []
    listed = ", ".join(missing[: get_setting("ats.keywords_listed")])
    message = (
        f"{len(missing)} of {len(keywords)} keywords of the job description are missing, "
        f"such as {listed}."
    )
    return score, [("keywords_missing", message, PART_SCORE_MAX - score)]


def _has_heading(lines, headings):
    longest = get_setting("ats.heading_max_length")
    wanted = {" ".join(heading.split()) for heading in headings}
    for line in lines:
        words = " ".join(re.sub(r"[^\w\s&]", " ", line.lower()).split())
        if words and len(line) <= longest and words in wanted:
            return True
    return False


def _section_part(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    each = PART_SCORE_MAX / CHECKS_PER_SECTIONS_PART
    score, lost = 0, []
    if EMAIL.search(text) or PHONE.search(text):
        score += each
    else:
        lost.append(("contact_missing", "No email address or phone number was found.", each))
    for _name, setting, message in SECTIONS:
        if _has_heading(lines, get_setting(setting)):
            score += each
        else:
            lost.append((f"{_name}_missing", message, each))
    return score, lost


def _readable_share(text):
    visible = [character for character in text if not character.isspace()]
    if not visible:
        return 0
    readable = sum(unicodedata.category(c)[0] not in UNREADABLE_CATEGORIES for c in visible)
    return 100 * readable / len(visible)


def readability_part(text):
    each = PART_SCORE_MAX / CHECKS_PER_READABILITY_PART
    words = len(text.split())
    lines = [line.split() for line in text.splitlines() if line.strip()]
    per_line = sorted(len(line) for line in lines)
    median = per_line[len(per_line) // 2] if per_line else 0
    checks = (
        (words >= get_setting("ats.min_words"), "text_too_short", "The CV has very little text."),
        (words <= get_setting("ats.max_words"), "text_too_long", "The CV is very long."),
        (
            _readable_share(text) >= get_setting("ats.min_readable_percent"),
            "unreadable_characters",
            "Many symbols or special characters could not be read.",
        ),
        (
            median >= get_setting("ats.min_words_per_line"),
            "broken_lines",
            "The text is split into very short lines, which suggests tables or columns.",
        ),
    )
    score, lost = 0, []
    for passed, code, message in checks:
        if passed:
            score += each
        else:
            lost.append((code, message, each))
    return score, lost


def _formatting_part(layout):
    each = PART_SCORE_MAX / CHECKS_PER_FORMATTING_PART
    score, lost = 0, []
    if layout.image_pages == 0:
        score += each
    else:
        lost.append(
            ("text_in_images", "Some pages are pictures of text, which a system cannot read.", each)
        )
    if layout.page_count is None or layout.page_count <= get_setting("ats.max_pages"):
        score += each
    else:
        lost.append(("too_many_pages", f"The CV has {layout.page_count} pages.", each))
    return score, lost


def score_cv(text, job_description, layout=None):
    """The ATS score of a CV's text and file layout against a job description."""
    parts = (
        ("ats.weight_keywords", _keyword_part(text, job_description)),
        ("ats.weight_sections", _section_part(text)),
        ("ats.weight_readability", readability_part(text)),
        ("ats.weight_formatting", _formatting_part(layout or Layout())),
    )
    weights = [get_setting(name) for name, _ in parts]
    total_weight = sum(weights) or 1
    score = (
        sum(weight * part[0] for weight, (_, part) in zip(weights, parts, strict=True))
        / total_weight
    )
    reasons = []
    for weight, (_, (_part_score, lost)) in zip(weights, parts, strict=True):
        for code, message, lost_points in lost:
            points = round(weight / total_weight * lost_points, 1)
            if points > 0:
                reasons.append(Reason(code, message, points))
    reasons.sort(key=lambda reason: -reason.points)  # a stable sort: equal losses keep their order
    return AtsResult(
        score=min(PART_SCORE_MAX, max(0, round(score))),
        reasons=reasons[: get_setting("ats.reasons_shown")],
    )
