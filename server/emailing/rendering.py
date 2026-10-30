from datetime import UTC

from django.template.loader import render_to_string

from .catalog import CATALOG
from .links import validate_link


def format_moment(moment):
    """ "30 October 2026, 15:20 UTC": when something happened, as the emails say it."""
    return moment.astimezone(UTC).strftime("%d %B %Y, %H:%M UTC").lstrip("0")


def duration_text(amount, unit):
    """ "1 hour", "24 hours": the wording the emails use for how long a link works."""
    return f"{amount} {unit}" if amount == 1 else f"{amount} {unit}s"


def render_email(template_name, values):
    """(subject, plain text, html) for one email. Mistakes in the calling code (an unknown
    template, a missing value, a foreign link) raise ValueError: they are bugs to fix, not
    something to retry."""
    if template_name not in CATALOG:
        raise ValueError(f"Unknown email template: {template_name}")
    template = CATALOG[template_name]
    missing = [name for name in template.variables if name not in values]
    if missing:
        raise ValueError(f"Email {template_name} needs: {', '.join(missing)}")
    validate_link(values["link"])
    filled = {name: str(values[name]) for name in template.variables}
    page = {
        "heading": template.heading.format(**filled),
        "paragraphs": [text.format(**filled) for text in template.paragraphs],
        "button_label": template.button_label,
        "link": filled["link"],
    }
    # A line break in a subject would let a name inject mail headers.
    subject = " ".join(template.subject.format(**filled).split())
    return (
        subject,
        render_to_string("emailing/message.txt", page),
        render_to_string("emailing/message.html", page),
    )
