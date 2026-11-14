"""Turning the text of a CV into a profile, once.

The profile and the contact details are saved together, with the model and prompt version that
made them. A CV that already has a profile is never read again, so a retry after a later
failure and every re-scoring cost no AI tokens. Nothing from the CV or the AI's answer is
logged.
"""

import logging

from django.db import transaction

from ai.client import call_ai
from plans.limits import check_ai_allowed
from platform_settings.service import get_setting

from .models import CvContact, CvProfile
from .processing import PermanentFailure, StepContext, register_step
from .profile_checks import UnusableAnswer, check_answer

logger = logging.getLogger(__name__)

UNUSABLE_REASON = "We could not read the details of this CV. You can retry it."
AI_PAUSED_REASON = "AI reading is paused for this period. You can retry it later."


def read_profile(cv_file, cv_text):
    """The CV's profile, from the AI unless one is already saved. An answer that is invalid or
    incomplete is asked for once more (setting), then the CV fails with a reason."""
    existing = CvProfile.objects.filter(cv_file=cv_file).first()
    if existing:
        return existing
    if not check_ai_allowed(cv_file.company_id).allowed:
        raise PermanentFailure(AI_PAUSED_REASON)
    project = cv_file.project
    tries = 1 + get_setting("ai.invalid_answer_retries")
    for _ in range(tries):
        answer = call_ai(
            cv_file.company_id,
            model=project.reading_model,
            instructions=get_setting("ai.cv_reading_prompt"),
            text=cv_text,
            project_id=project.pk,
            cv_id=cv_file.pk,
            max_output_tokens=get_setting("ai.cv_reading_max_output_tokens"),
        )
        try:
            profile, contact = check_answer(answer.text, cv_text)
        except UnusableAnswer:
            logger.warning("The AI gave a CV profile that could not be used.")
            continue
        return _save(cv_file, project, profile, contact)
    raise PermanentFailure(UNUSABLE_REASON)


def _save(cv_file, project, profile, contact):
    with transaction.atomic():
        saved, _ = CvProfile.objects.get_or_create(
            cv_file=cv_file,
            defaults={
                "company_id": cv_file.company_id,
                "content": profile,
                "model": project.reading_model,
                "prompt_version": project.prompt_version,
            },
        )
        CvContact.objects.get_or_create(
            cv_file=cv_file, defaults={"company_id": cv_file.company_id, **contact}
        )
    return saved


def read_with_ai(context: StepContext):
    """Slot `ai_reading`: the profile of the CV from the text the earlier step read."""
    read_profile(context.cv_file, context.state["text"])


register_step("ai_reading", read_with_ai)
