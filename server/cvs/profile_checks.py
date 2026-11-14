"""Checking what the AI says about a CV against the CV's own text.

The AI's answer is untrusted. Its shape is checked strictly (a wrong shape means the answer is
unusable), and every fact in it must be found in the CV text: anything that is not found is
invented and removed. Only known fields are copied out, so extra fields the AI adds (age,
gender, a photo description) never reach the profile.
"""

import json
import re
from datetime import date

from platform_settings.service import get_setting

LIST_FIELDS = ("skills", "certifications", "languages")
CONTACT_FIELDS = ("name", "email", "phone", "address")
DATE_FORM = re.compile(r"^(\d{4})(?:-(\d{2}))?$")
PRESENT = "present"
MONTHS_IN_YEAR = 12
DIGITS = re.compile(r"\D+")


class UnusableAnswer(Exception):
    """The answer is not valid JSON of the expected shape, or nothing in it survives."""


def _text(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def _found(item, text):
    """Whether the item appears in the CV text as whole words, ignoring case and spacing."""
    words = item.split()
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _checked_strings(values, text):
    longest = get_setting("profile.item_max_length")
    seen, kept = set(), []
    for value in values:
        item = _text(value)
        if not item or len(item) > longest or item.lower() in seen or not _found(item, text):
            continue
        seen.add(item.lower())
        kept.append(item)
    return kept[: get_setting("profile.max_items")]


def _list(answer, name):
    """The list under `name`; a missing or wrongly typed one makes the answer unusable."""
    values = answer.get(name)
    if not isinstance(values, list):
        raise UnusableAnswer(name)
    return values


def _checked_date(value, text):
    """'YYYY', 'YYYY-MM' or 'present'; a date whose year is not in the CV is removed."""
    value = _text(value).lower()
    if value == PRESENT:
        return value
    matched = DATE_FORM.match(value)
    if not matched:
        return None
    year, month = matched.groups()
    if month and not 1 <= int(month) <= MONTHS_IN_YEAR:
        return None
    return value if _found(year, text) else None


def _checked_jobs(values, text):
    jobs, seen = [], set()
    longest = get_setting("profile.item_max_length")
    for value in values:
        if not isinstance(value, dict):
            continue
        title = _text(value.get("title"))
        if not title or len(title) > longest or not _found(title, text):
            continue
        job = {
            "title": title,
            "start": _checked_date(value.get("start"), text),
            "end": _checked_date(value.get("end"), text),
        }
        key = (title.lower(), job["start"], job["end"])
        if key not in seen:
            seen.add(key)
            jobs.append(job)
    return jobs[: get_setting("profile.max_items")]


def _checked_education(values, text):
    entries, seen = [], set()
    longest = get_setting("profile.item_max_length")
    for value in values:
        if not isinstance(value, dict):
            continue
        degree, institution = _text(value.get("degree")), _text(value.get("institution"))
        degree = degree if degree and len(degree) <= longest and _found(degree, text) else ""
        institution = (
            institution
            if institution and len(institution) <= longest and _found(institution, text)
            else ""
        )
        key = (degree.lower(), institution.lower())
        if (degree or institution) and key not in seen:
            seen.add(key)
            entries.append({"degree": degree, "institution": institution})
    return entries[: get_setting("profile.max_items")]


def month_number(value, *, end):
    """A month count for 'YYYY' or 'YYYY-MM'; a bare year means its first (or last) month."""
    year, _, month = value.partition("-")
    default = MONTHS_IN_YEAR if end else 1
    return int(year) * MONTHS_IN_YEAR + int(month or default) - 1


def years_of_experience(jobs, today=None):
    """Counted from the checked jobs, with overlapping jobs counted once, so the figure rests
    on dates found in the CV and not on a number the AI made up. None when no job has a start."""
    today = today or date.today()
    now = today.year * MONTHS_IN_YEAR + today.month - 1
    spans = []
    for job in jobs:
        if not job["start"]:
            continue
        start = month_number(job["start"], end=False)
        ending = job["end"]
        stop = now if ending in (PRESENT, None) else month_number(ending, end=True)
        spans.append((start, min(max(stop, start), now)))
    if not spans:
        return None
    months, last_end = 0, None
    for start, stop in sorted(spans):
        if last_end is None or start > last_end:
            months += stop - start + 1
            last_end = stop
        elif stop > last_end:
            months += stop - last_end
            last_end = stop
    return round(months / MONTHS_IN_YEAR, 1)


def _checked_contact(answer, text):
    """Only the contact details that the CV text really contains."""
    given = answer.get("contact")
    given = given if isinstance(given, dict) else {}
    contact = {field: _text(given.get(field)) for field in CONTACT_FIELDS}
    flat = text.lower()
    digits_in_cv = DIGITS.sub("", text)
    if contact["email"] and contact["email"].lower() not in flat:
        contact["email"] = ""
    phone_digits = DIGITS.sub("", contact["phone"])
    if contact["phone"] and (len(phone_digits) < 5 or phone_digits not in digits_in_cv):
        contact["phone"] = ""
    for field in ("name", "address"):
        if contact[field] and not _found(contact[field], text):
            contact[field] = ""
    return contact


def _checked_summary(value, contact):
    """The summary is the AI's own wording, so it cannot be matched to the text. It is kept
    only when it is short enough and carries none of the contact details."""
    summary = _text(value)
    if not summary or len(summary) > get_setting("profile.summary_max_length"):
        return ""
    lowered = summary.lower()
    if any(detail and detail.lower() in lowered for detail in contact.values()):
        return ""
    return summary


def _without_contact(profile, contact):
    """Drops any entry that is, or holds, a contact detail: the profile used for scoring never
    carries them, whichever list the AI put them in."""
    details = [detail.lower() for detail in contact.values() if detail]

    def clean(entry):
        return not any(detail in json.dumps(entry).lower() for detail in details)

    for name in (*LIST_FIELDS, "jobs", "education"):
        profile[name] = [entry for entry in profile[name] if clean(entry)]


def check_answer(raw_text, cv_text):
    """(profile, contact) from the AI's answer with invented facts removed. Raises
    `UnusableAnswer` for an answer of the wrong shape or one with no skills and no job titles."""
    try:
        answer = json.loads(raw_text)
    except (TypeError, ValueError) as error:
        raise UnusableAnswer("not json") from error
    if not isinstance(answer, dict) or not isinstance(answer.get("summary"), str):
        raise UnusableAnswer("shape")
    lists = {name: _list(answer, name) for name in (*LIST_FIELDS, "jobs", "education")}
    contact = _checked_contact(answer, cv_text)
    jobs = _checked_jobs(lists["jobs"], cv_text)
    profile = {name: _checked_strings(lists[name], cv_text) for name in LIST_FIELDS}
    profile.update(
        jobs=jobs,
        education=_checked_education(lists["education"], cv_text),
        summary=_checked_summary(answer["summary"], contact),
    )
    _without_contact(profile, contact)
    profile["years_of_experience"] = years_of_experience(profile["jobs"])
    if not profile["skills"] and not profile["jobs"]:
        raise UnusableAnswer("nothing usable")
    return profile, contact
