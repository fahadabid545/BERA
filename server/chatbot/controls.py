"""The chatbot's settings: the on/off switch, the model, the prompt version and the limits.

They are ordinary platform settings (so the later chat feature only has to read them with
`get_setting`), edited together on the admin Chatbot page. The model comes from the models list
and the prompt version from the prompt versions (kind "chatbot"). The chatbot cannot be switched
on without a model. Every change is audited with the old and new values.
"""

from django.db import transaction

from ai.models import AiModel, PromptVersion
from ai.prompt_versions import CHATBOT, exists
from audit.service import record
from core.errors import form_error
from platform_settings.definitions import DEFINITIONS
from platform_settings.models import PlatformSetting
from platform_settings.service import clear_cache, get_setting

# field name on the page -> platform setting
SETTINGS = {
    "enabled": "chatbot.enabled",
    "model": "chatbot.model",
    "prompt_version": "ai.chatbot_prompt_version",
    "visitor_questions_per_hour": "chatbot.visitor_questions_per_hour",
    "max_question_length": "chatbot.max_question_length",
    "max_answer_length": "chatbot.max_answer_length",
    "daily_token_cap": "chatbot.daily_token_cap",
}
NEEDS_MODEL = "Choose a model before switching the chatbot on."
MODEL_NOT_ON = "Choose a model that is switched on."
NO_SUCH_VERSION = "There is no such prompt version."
NOT_ALLOWED = "This value is not allowed."


def describe():
    return {
        **{field: get_setting(key) for field, key in SETTINGS.items()},
        "models": list(AiModel.objects.filter(enabled=True).values_list("name", flat=True)),
        "prompt_versions": list(
            PromptVersion.objects.filter(kind=CHATBOT).values_list("number", flat=True)
        ),
    }


def _problems(values):
    problems = {}
    for field, key in SETTINGS.items():
        if not DEFINITIONS[key].is_valid(values[field]):
            problems[field] = NOT_ALLOWED
    model = values["model"]
    if model and "model" not in problems:
        if not AiModel.objects.filter(name=model, enabled=True).exists():
            problems["model"] = MODEL_NOT_ON
    if values["enabled"] is True and not model:
        problems["enabled"] = NEEDS_MODEL
    if "prompt_version" not in problems and not exists(CHATBOT, values["prompt_version"]):
        problems["prompt_version"] = NO_SUCH_VERSION
    return problems


def update(admin, values):
    """Saves all the chatbot settings at once (all or none) and returns the new state."""
    if problems := _problems(values):
        raise form_error(problems)
    with transaction.atomic():
        changes = {}
        for field, key in SETTINGS.items():
            old = get_setting(key)
            if values[field] != old:
                PlatformSetting.objects.update_or_create(key=key, defaults={"value": values[field]})
                changes[field] = {"old": old, "new": values[field]}
        if changes:
            record("admin.chatbot_settings_changed", actor=admin, changes=changes)
    clear_cache()
    return describe()
