"""Deleting a project: the one central function that removes everything belonging to it.

Every ticket that stores project data (files, candidates, scores...) must, in the same change:
  1. register its data here with `register_project_data` (removing files from storage too), and
  2. add its name to `EXPECTED_REGISTRATIONS` in `projects/tests/test_project_deletion.py`.
A guard test fails when a model that belongs to a project is neither registered nor listed as
kept on purpose (the usage ledger, which stays in history).

Work that is running for the project (reading, scoring) registers a stopper with
`register_work_stopper`; deletion stops it before anything is removed.
"""

from django.db import transaction

from activity import service as activity
from companies.models import Company

# name -> function(company_id, project_id) that removes that kind of project data for good
DATA_REMOVERS = {}
# name -> function(company_id, project_id) that stops running work and returns when it is safe
WORK_STOPPERS = {}


def register_project_data(name, remover):
    DATA_REMOVERS[name] = remover


def register_work_stopper(name, stopper):
    WORK_STOPPERS[name] = stopper


def delete_project(owner, project):
    """Stops the project's work, removes all its data, then the project itself, and logs the
    deletion by identifier only (no title and no names of people)."""
    company_id, project_id = project.company_id, project.pk
    with transaction.atomic():
        # The company row lock keeps a parallel create or restore from miscounting meanwhile.
        Company.objects.select_for_update().get(pk=company_id)
        for stop in WORK_STOPPERS.values():
            stop(company_id, project_id)
        for remove in DATA_REMOVERS.values():
            remove(company_id, project_id)
        project.delete()
        activity.record(
            "project_deleted",
            company_id=company_id,
            actor=owner,
            target_kind="project",
            target_id=project_id,
        )
