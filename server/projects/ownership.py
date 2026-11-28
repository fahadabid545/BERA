"""Handing a project to another team member. The owner of a project is the person who created
it; it is shown on the project list and decides who is named for it, not who may open it."""

from django.db import transaction

from activity import service as activity
from companies.models import CompanyUser
from core.errors import form_error
from core.scoping import get_in_company

from .models import Project


def change_project_owner(actor, project, new_owner_id):
    """Makes the active team member `new_owner_id` the project's owner and logs it. A person of
    another company is "not found"; a removed or blocked member, or the current owner, is a
    form error."""
    with transaction.atomic():
        new_owner = get_in_company(CompanyUser.objects.all(), project.company_id, pk=new_owner_id)
        if new_owner.status != CompanyUser.Status.ACTIVE:
            raise form_error({"owner_id": "Choose an active team member."})
        if new_owner.pk == project.created_by_id:
            raise form_error({"owner_id": "This person already owns the project."})
        Project.objects.filter(pk=project.pk).update(created_by=new_owner)
        activity.record(
            "project_owner_changed",
            company_id=project.company_id,
            actor=actor,
            target_kind="project",
            target_id=project.pk,
            details={"new_owner_name": new_owner.name},
        )
    project.refresh_from_db()
    return project
