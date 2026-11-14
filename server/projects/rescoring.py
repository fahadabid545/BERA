"""What changing a project's requirements means for the CVs already scored: the estimate shown
before saving, and starting the re-scoring after it. The work itself is in `cvs/rescoring.py`
(cvs builds on projects, so it is imported when used)."""


def changed_requirement_count(project, items):
    """How many requirements of the new list are new or have new wording (the only ones that
    need the AI; weights, kinds and order never do)."""
    from cvs.rescoring import changed_texts

    return changed_texts(project, items)


def rescoring_estimate(project, items):
    """The CVs that would run again, the approximate cost, and whether the plan's AI allowance
    would be passed."""
    from cvs.rescoring import estimate

    return estimate(project, items)


def start_rescoring(project):
    """Marks the scored candidates Outdated and queues their CVs; returns how many were queued."""
    from cvs.rescoring import start

    return start(project)


def wake_workers(queued):
    from cvs.rescoring import wake

    wake(queued)
