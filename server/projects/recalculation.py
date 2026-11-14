"""Recalculating a project's scores after its scoring settings or requirement weights change.

Changing weights, the cap switch or a requirement's weight never needs the AI: the
per-requirement results are kept, so scores are only recombined (see `cvs/scoring.py`)."""


def recalculate_scores(project):
    """Recombines the project's stored results with its current settings. Returns how many
    candidates' scores changed."""
    from cvs.scoring import recalculate_project  # cvs depends on projects, not the reverse

    return recalculate_project(project)
