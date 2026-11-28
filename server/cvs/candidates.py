"""The candidate record: one per CV that has been read.

The `candidate_record` step creates it after the profile and the fairness guard, so it exists
before scoring. It is created once: a retry finds the record that is already there. Failed CVs
have no candidate; they stay in the project's file list with their reason and a Retry button.
"""

from django.db import transaction
from django.db.models import Max

from projects.deletion import register_project_data
from projects.models import Project

from .models import Candidate, CvFile
from .processing import StepContext, register_step
from .service import remove_cv_file


def create_candidate(cv_file):
    """The candidate of a CV that has its profile and contact details; the same one if it
    already exists."""
    with transaction.atomic():
        # The project row is locked so two CVs finishing together never take the same number.
        Project.objects.select_for_update().get(pk=cv_file.project_id)
        existing = Candidate.objects.filter(cv_file=cv_file).first()
        if existing:
            return existing
        last = Candidate.objects.filter(project_id=cv_file.project_id).aggregate(Max("number"))
        return Candidate.objects.create(
            cv_file=cv_file,
            company_id=cv_file.company_id,
            project_id=cv_file.project_id,
            profile=cv_file.profile,
            contact=cv_file.contact,
            number=(last["number__max"] or 0) + 1,
        )


def remove_candidate(candidate):
    """Removes the candidate with everything of theirs: the file in storage, the CV record, the
    profile, the contact details and (through their cascading links) scores and notes. The usage
    history stays."""
    remove_cv_file(candidate.cv_file)


def _remove_for_project(company_id, project_id):
    for cv_file in CvFile.objects.filter(
        company_id=company_id, project_id=project_id, candidate__isnull=False
    ):
        remove_candidate(cv_file.candidate)


def make_the_candidate(context: StepContext):
    """Slot `candidate_record`: the CV has been read, so it becomes a candidate."""
    create_candidate(context.cv_file)


register_step("candidate_record", make_the_candidate)
register_project_data("Candidate", _remove_for_project)
