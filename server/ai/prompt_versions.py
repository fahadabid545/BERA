"""The numbered versions of the AI's instructions, for reading CVs and for scoring.

A new version never changes an existing project: a project pins the numbers it was created
with. Which version new projects start with is chosen by an admin ("current"). An admin can
move one project to another version. A version that is current or pinned by a project cannot
be deleted. Every change is audited.
"""

import difflib

from django.db import transaction

from audit.service import record
from core.errors import AppError
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting
from projects.models import Project

from .models import PromptCounter, PromptVersion

READING, SCORING = PromptVersion.READING, PromptVersion.SCORING
KINDS = (READING, SCORING)
CURRENT_SETTING = {READING: "ai.reading_prompt_version", SCORING: "ai.scoring_prompt_version"}
PROJECT_FIELD = {READING: "reading_prompt_version", SCORING: "scoring_prompt_version"}

IN_USE_CODE = "prompt_in_use"
IN_USE_MESSAGE = "This version is in use, so it cannot be deleted."
NOT_FOUND_MESSAGE = "There is no such version."
CHANGE_NOTHING = "Nothing was changed."


def _version(kind, number):
    try:
        return PromptVersion.objects.get(kind=kind, number=number)
    except PromptVersion.DoesNotExist as error:
        raise AppError("prompt_not_found", NOT_FOUND_MESSAGE, status_code=404) from error


def prompt_text(kind, number):
    """The instructions of one version (what a project's pin points at)."""
    return _version(kind, number).text


def current_number(kind):
    return get_setting(CURRENT_SETTING[kind])


def usage_of(version):
    return {
        "current": current_number(version.kind) == version.number,
        "projects": Project.objects.filter(**{PROJECT_FIELD[version.kind]: version.number}).count(),
    }


def describe(version, *, with_text=True):
    return {
        "kind": version.kind,
        "number": version.number,
        "created_at": version.created_at.isoformat(),
        **({"text": version.text} if with_text else {}),
        **usage_of(version),
    }


def overview():
    return {
        kind: [describe(version) for version in PromptVersion.objects.filter(kind=kind)]
        for kind in KINDS
    }


def create_version(admin, *, kind, text):
    """Adds the next version of `kind`; it is not used by new projects until it is made current."""
    with transaction.atomic():
        counter, _ = PromptCounter.objects.select_for_update().get_or_create(kind=kind)
        counter.last_number += 1
        counter.save(update_fields=["last_number"])
        version = PromptVersion.objects.create(kind=kind, number=counter.last_number, text=text)
        record(
            "admin.prompt_created",
            actor=admin,
            details={"kind": kind, "number": version.number},
        )
    return version


def make_current(admin, *, kind, number, reason):
    """New projects start with this version. Existing projects are not touched."""
    with transaction.atomic():
        version = _version(kind, number)
        before = current_number(kind)
        if before == version.number:
            raise AppError("nothing_changed", CHANGE_NOTHING, status_code=400)
        PlatformSetting.objects.update_or_create(
            key=CURRENT_SETTING[kind], defaults={"value": version.number}
        )
        record(
            "admin.prompt_made_current",
            actor=admin,
            reason=reason,
            details={"kind": kind},
            changes={"current_version": {"old": before, "new": version.number}},
        )
    return version


def delete_version(admin, *, kind, number, reason):
    with transaction.atomic():
        version = _version(kind, number)
        usage = usage_of(version)
        if usage["current"] or usage["projects"]:
            raise AppError(IN_USE_CODE, IN_USE_MESSAGE, status_code=409, details={"usage": usage})
        version.delete()
        record(
            "admin.prompt_deleted",
            actor=admin,
            reason=reason,
            details={"kind": kind, "number": number},
        )


def move_project(admin, *, project_id, kind, number, reason):
    """An admin action: the project uses another version from now on."""
    with transaction.atomic():
        project = Project.objects.select_for_update().filter(pk=project_id).first()
        if project is None:
            raise AppError("project_not_found", "There is no such project.", status_code=404)
        _version(kind, number)
        field = PROJECT_FIELD[kind]
        before = getattr(project, field)
        if before == number:
            raise AppError("nothing_changed", CHANGE_NOTHING, status_code=400)
        setattr(project, field, number)
        project.save(update_fields=[field, "updated_at"])
        record(
            "admin.project_prompt_moved",
            actor=admin,
            company_id=project.company_id,
            reason=reason,
            details={"kind": kind, "project_id": str(project.pk)},
            changes={f"{kind}_version": {"old": before, "new": number}},
        )
    return project


def compare(kind, first, second):
    """The two versions' texts as rows to show side by side: each row has the left and right
    line (empty where one side has no line there) and whether they differ."""
    left = _version(kind, first).text.splitlines()
    right = _version(kind, second).text.splitlines()
    rows = []
    for tag, a_start, a_end, b_start, b_end in difflib.SequenceMatcher(
        None, left, right, autojunk=False
    ).get_opcodes():
        left_lines, right_lines = left[a_start:a_end], right[b_start:b_end]
        for position in range(max(len(left_lines), len(right_lines))):
            rows.append(
                {
                    "left": left_lines[position] if position < len(left_lines) else "",
                    "right": right_lines[position] if position < len(right_lines) else "",
                    "changed": tag != "equal",
                }
            )
    return {"kind": kind, "left": first, "right": second, "rows": rows}
