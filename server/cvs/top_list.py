"""The top candidates of a project, marked on the candidate list.

The top N is the project's scoring setting (default and plan cap in `projects/scoring_settings.py`),
taken among the scored candidates that are not rejected, best AI score first. It is worked out
from the stored scores on every look, so it is always the current one. Ties at the cut-off all
count: everyone with the N-th best score is in, so the list can hold more than N, and `tied` says
so for the note on the page. When there are fewer scored candidates than N, all of them are in.
"""

from projects.scoring_settings import effective_settings

from .models import Candidate, CandidateScore


def top_list(project):
    """{"n", "cutoff", "included", "tied"}: `cutoff` is the lowest score that is in the top
    (None when fewer than N are scored, so every scored candidate is in)."""
    n = effective_settings(project)["top_n"]
    scored = CandidateScore.objects.filter(
        company_id=project.company_id, candidate__project=project
    ).exclude(candidate__stage=Candidate.Stage.REJECTED)
    nth = scored.order_by("-score").values_list("score", flat=True)[n - 1 : n]
    cutoff = nth[0] if nth else None
    included = scored.count() if cutoff is None else scored.filter(score__gte=cutoff).count()
    return {"n": n, "cutoff": cutoff, "included": included, "tied": included > n}


def in_top(top, score, stage):
    """Whether a candidate with this score and stage is in the top (not rejected, scored)."""
    if score is None or stage == Candidate.Stage.REJECTED:
        return False
    return top["cutoff"] is None or score >= top["cutoff"]
