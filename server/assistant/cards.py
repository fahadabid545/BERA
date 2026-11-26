"""The candidate details the screen shows next to an answer, read live from the record.

The AI never sees these (see `tools.py`). They are put beside its answer by the app, so the person
gets the name, contact details and numbers while the AI only ever worked with references and
scores. Because they are read each time, a candidate who was deleted or removed by the retention
rules is simply no longer here, and nothing is left behind in the saved chat.
"""

from cvs.models import Candidate

from .tools import candidate_reference


def _years(candidate):
    years = candidate.profile.content.get("years_of_experience")
    return years if isinstance(years, int | float) and not isinstance(years, bool) else None


def describe(company_id, candidate_ids):
    """{reference: card} for the candidates of this company that still exist."""
    if not candidate_ids:
        return {}
    found = Candidate.objects.filter(company_id=company_id, pk__in=candidate_ids).select_related(
        "contact", "profile", "score", "ats_score", "project"
    )
    cards = {}
    for candidate in found:
        score = getattr(candidate, "score", None)
        ats = getattr(candidate, "ats_score", None)
        cards[candidate_reference(candidate.pk)] = {
            "candidate_id": str(candidate.pk),
            "project_id": str(candidate.project_id),
            "project_title": candidate.project.title,
            "name": candidate.contact.name,
            "email": candidate.contact.email,
            "phone": candidate.contact.phone,
            "years_of_experience": _years(candidate),
            "score": f"{score.score:.1f}" if score else None,
            "grade": score.grade if score else None,
            "label": score.label if score else None,
            "ats_score": ats.score if ats else None,
            "stage": candidate.stage,
        }
    return cards
