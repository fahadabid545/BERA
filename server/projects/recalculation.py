"""Recalculating a project's scores after its scoring settings change.

Changing weights, the recommendation threshold or the top-N size never needs the AI: the
per-requirement results are kept, so scores are only recombined. The Score calculation ticket
fills this in; until CVs are scored there is nothing to recalculate."""


def recalculate_scores(project):
    """Recombines the project's stored results with its current settings. Returns how many
    candidates' scores changed."""
    return 0
