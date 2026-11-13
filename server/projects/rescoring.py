"""What changing a project's requirements would cost in re-scoring. The Re-scoring ticket
fills `rescoring_estimate` in once CVs are scored; until then nothing has been scored."""

from decimal import Decimal


def rescoring_estimate(project):
    """How many scored CVs would need scoring again, and the estimated cost of doing it."""
    return {"cvs": 0, "estimated_cost": Decimal(0)}
