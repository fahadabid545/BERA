"""The fairness guard: personal details are removed from CV text before it is scored.

`remove_personal_details` is the one function every scoring input goes through (Requirement
evaluation must call it); the `fairness_guard` step runs it for a CV in the pipeline. It makes
no AI call. It removes, wherever they sit in the text (headers, footers, tables, the middle of a
sentence):

- the CV's own saved name, address, email and phone (see `CvContact`), as typed or reformatted;
- the value after a personal-detail label such as "Date of birth:", "Nationality:" or
  "Gender:", also when the value is on the next line or the label is followed by a date or an
  age and no colon;
- a date after "born";
- any email address or phone number.

Unlabelled words (a nationality, a religion, "married") are deliberately left alone, because
removing them would also cut real text ("Indian cuisine", a company name). Photos are images
and are not part of the text this function sees. Contact details are kept apart for the
recruiter's view and never go on to scoring.
"""

import re

from platform_settings.service import get_setting

from .duplicates import EMAIL
from .models import CvContact
from .processing import StepContext, register_step

MARK = "\x00"  # where something was removed, so the line can be tidied afterwards
DELIMITERS = "|;•·"
BULLETS = "-*•·▪►"
SEPARATORS_TO_TRIM = " \t|;•·,:-–—"
MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
ORDINAL = r"(?:st|nd|rd|th)?"
DATE = (
    r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2}"
    rf"|\d{{1,2}}{ORDINAL}\s+(?:of\s+)?{MONTH}\s+\d{{4}}"
    rf"|{MONTH}\s+\d{{1,2}}{ORDINAL},?\s+\d{{4}}|{MONTH}\s+\d{{4}}|\d{{4}})"
)
# A phone number written with a plus, with brackets, or as three or more groups of digits;
# two groups ("2014 - 2017") are a range of years and stay.
PHONE = re.compile(
    r"(?<![\w.])(?:\+\d[\d\s().-]{5,}\d|\(\d{2,5}\)[\d\s.-]{4,}\d"
    r"|\d{2,5}(?:[\s.-]\d{2,5}){2,}|\d{7,15})(?![\w])"
)


def _words_pattern(text):
    """The text as a pattern that ignores case and how the spaces are written."""
    return r"\s+".join(re.escape(word) for word in text.split())


def _label_group():
    labels = sorted(get_setting("fairness.labels"), key=len, reverse=True)
    return "(?:" + "|".join(_words_pattern(label) for label in labels) + ")"


def _remove_labelled(text):
    label, bullet = _label_group(), rf"[ \t]*[{BULLETS}]?[ \t]*"
    # A label alone on its line has its value on the next line.
    alone = re.compile(rf"^{bullet}{label}[ \t]*:?[ \t]*\n[ \t]*[^\n]*", re.IGNORECASE | re.M)
    text = alone.sub(MARK, text)
    with_value = re.compile(
        rf"(?P<start>^|[{DELIMITERS}]){bullet}{label}(?![\w])"
        rf"(?:[ \t]*[:=–—-][ \t]*|[ \t]+(?=(?:{DATE}|\d{{1,3}})(?!\w)))[^\n{DELIMITERS}]*",
        re.IGNORECASE | re.M,
    )
    return with_value.sub(lambda found: found["start"] + MARK, text)


def _remove_birth_dates(text):
    words = "|".join(re.escape(word) for word in get_setting("fairness.born_words"))
    pattern = re.compile(rf"(?<!\w)(?:{words})(?!\w)[ \t]*(?:on|in|:)?[ \t]*{DATE}", re.IGNORECASE)
    return pattern.sub(MARK, text)


def _known_values(contact):
    """The patterns for what the CV's own contact record says, most specific first."""
    name, address = _field(contact, "name"), _field(contact, "address")
    email, phone = _field(contact, "email"), _field(contact, "phone")
    patterns = []
    if email:
        patterns.append(re.escape(email))
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= get_setting("fairness.phone_min_digits"):
        patterns.append(r"\+?\(?(?<!\d)" + r"\D*".join(digits) + r"(?!\d)")
    if address:
        parts = [part for part in re.split(r"[,\n]+", address) if part.strip()]
        patterns.append(r"[\s,]+".join(_words_pattern(part) for part in parts))
    if name:
        patterns.append(_words_pattern(name))
        shortest = get_setting("fairness.min_name_part_length")
        patterns.extend(re.escape(part) for part in name.split() if len(part) >= shortest)
    return [re.compile(rf"(?<!\w)(?:{pattern})(?!\w)", re.IGNORECASE) for pattern in patterns]


def _field(contact, name):
    value = contact.get(name, "") if isinstance(contact, dict) else getattr(contact, name, "")
    return (value or "").strip()


def _tidy(line):
    """What is left of a line that had something removed: no stray separators, or no line."""
    line = line.replace(MARK, " ")
    line = re.sub(rf"\s*([{DELIMITERS}])(?:\s*[{DELIMITERS}])+", r" \1", line)
    line = re.sub(r"[ \t]{2,}", " ", line).strip(SEPARATORS_TO_TRIM)
    return line if re.search(r"\w", line) else None


def remove_personal_details(text, contact=None):
    """The text with personal details and contact details removed, for scoring.

    `contact` is the CV's saved contact record (or a dict with name, email, phone and address);
    what it holds is removed wherever it appears. Lines that only held a removed detail are
    dropped; every other line keeps its words.
    """
    text = text.replace(MARK, "")
    text = _remove_labelled(text)
    # Emails and phones first, whole, so a name part cannot cut one in half.
    text = EMAIL.sub(MARK, text)
    text = _remove_phones(text)
    for pattern in _known_values(contact):
        text = pattern.sub(MARK, text)
    text = _remove_birth_dates(text)
    kept = []
    for line in text.split("\n"):
        if MARK not in line:
            kept.append(line)
        elif (tidy := _tidy(line)) is not None:
            kept.append(tidy)
    return "\n".join(kept)


def _remove_phones(text):
    smallest = get_setting("fairness.phone_min_digits")

    def replace(found):
        return MARK if len(re.sub(r"\D", "", found[0])) >= smallest else found[0]

    return PHONE.sub(replace, text)


def guard_the_text(context: StepContext):
    """Slot `fairness_guard`: the text scoring may see, kept in `scoring_text`. Scoring never
    reads `text`, which still holds the personal details."""
    contact = CvContact.objects.filter(cv_file=context.cv_file).first()
    context.state["scoring_text"] = remove_personal_details(context.state["text"], contact)


register_step("fairness_guard", guard_the_text)
