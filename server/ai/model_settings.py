"""The models list and the two choices (reading and scoring) that new projects start with.

Every change goes through here so the rules and the audit entry cannot be skipped. A project
pins the model names it was created with. Changing the choice never touches existing projects.
The one exception is disabling a model that is in use: it needs a replacement, and then the
choices and the projects that used it move to the replacement, in one step.
"""

from django.db import transaction

from audit.service import record
from core.errors import AppError
from platform_settings.models import PlatformSetting
from platform_settings.service import get_setting
from projects.models import Project

from .models import AiModel

READING, SCORING = "reading", "scoring"
CHOICES = {READING: "ai.reading_model", SCORING: "ai.scoring_model"}
PROJECT_FIELDS = {READING: "reading_model", SCORING: "scoring_model"}

IN_USE_CODE = "model_in_use"
IN_USE_MESSAGE = "This model is in use. Choose a replacement to disable it."
NOT_ENABLED = "Choose a model that is switched on."
NO_REPLACEMENT = "The replacement must be a different model that is switched on."
CHANGE_NOTHING = "Nothing was changed."


def _plain(value):
    return f"{value:.4f}" if hasattr(value, "quantize") else value


def chosen_names():
    return {role: get_setting(key) for role, key in CHOICES.items()}


def _choose(role, name):
    PlatformSetting.objects.update_or_create(key=CHOICES[role], defaults={"value": name})


def usage_of(model):
    """Where a model is in use: which choices point at it and how many projects pinned it."""
    chosen = chosen_names()
    return {
        "chosen_for": [role for role in CHOICES if chosen[role] == model.name],
        "projects": {
            role: Project.objects.filter(**{PROJECT_FIELDS[role]: model.name}).count()
            for role in CHOICES
        },
    }


def _is_in_use(usage):
    return bool(usage["chosen_for"]) or any(usage["projects"].values())


def describe(model):
    return {
        "id": model.pk,
        "name": model.name,
        "input_price_per_million": _plain(model.input_price_per_million),
        "output_price_per_million": _plain(model.output_price_per_million),
        "enabled": model.enabled,
        **usage_of(model),
    }


def overview():
    return {
        "models": [describe(model) for model in AiModel.objects.all()],
        "choice": chosen_names(),
    }


def add_model(admin, *, name, input_price, output_price, enabled=True):
    with transaction.atomic():
        if AiModel.objects.filter(name=name).exists():
            raise AppError(
                "model_exists",
                "A model with this name is already in the list.",
                status_code=400,
                fields={"name": "A model with this name is already in the list."},
            )
        model = AiModel.objects.create(
            name=name,
            input_price_per_million=input_price,
            output_price_per_million=output_price,
            enabled=enabled,
        )
        record("admin.model_added", actor=admin, details={"model": name, "enabled": enabled})
    return model


def _replacement_for(model, replacement_id):
    options = AiModel.objects.filter(enabled=True).exclude(pk=model.pk)
    chosen = options.filter(pk=replacement_id).first() if replacement_id else None
    if chosen is None:
        raise AppError(
            IN_USE_CODE,
            IN_USE_MESSAGE if options.exists() else NO_REPLACEMENT,
            status_code=409,
            details={
                "usage": usage_of(model),
                "replacements": [{"id": option.pk, "name": option.name} for option in options],
            },
        )
    return chosen


def _move_to(model, replacement):
    """The choices and the pinned projects that used `model` use `replacement` instead."""
    moved = {"chosen_for": [], "projects": 0}
    for role in CHOICES:
        if chosen_names()[role] == model.name:
            _choose(role, replacement.name)
            moved["chosen_for"].append(role)
        moved["projects"] += Project.objects.filter(**{PROJECT_FIELDS[role]: model.name}).update(
            **{PROJECT_FIELDS[role]: replacement.name}
        )
    return moved


def change_model(
    admin,
    model_id,
    *,
    reason,
    input_price=None,
    output_price=None,
    enabled=None,
    replacement_id=None,
):
    """Changes the prices and/or switches a model on or off. Prices apply to later calls only.
    Switching off a model in use needs `replacement_id`."""
    with transaction.atomic():
        model = AiModel.objects.select_for_update().get(pk=model_id)
        changes = {}
        for field, value in (
            ("input_price_per_million", input_price),
            ("output_price_per_million", output_price),
            ("enabled", enabled),
        ):
            if value is not None and getattr(model, field) != value:
                changes[field] = {"old": _plain(getattr(model, field)), "new": _plain(value)}
        if not changes:
            raise AppError("nothing_changed", CHANGE_NOTHING, status_code=400)
        moved = None
        if "enabled" in changes and not enabled and _is_in_use(usage_of(model)):
            moved = _move_to(model, _replacement_for(model, replacement_id))
        for field in changes:
            setattr(
                model,
                field,
                {
                    "enabled": enabled,
                    "input_price_per_million": input_price,
                    "output_price_per_million": output_price,
                }[field],
            )
        model.save()
        details = {"model": model.name}
        if moved:
            details.update(
                moved_choices=",".join(moved["chosen_for"]) or "none",
                moved_projects=moved["projects"],
            )
        record("admin.model_changed", actor=admin, reason=reason, details=details, changes=changes)
    return model


def select_models(admin, *, reading_id, scoring_id, reason):
    """Sets the models new projects start with. Both must be switched on."""
    with transaction.atomic():
        picked = {}
        for role, model_id in ((READING, reading_id), (SCORING, scoring_id)):
            model = AiModel.objects.filter(pk=model_id, enabled=True).first()
            if model is None:
                raise AppError(
                    "model_not_enabled",
                    NOT_ENABLED,
                    status_code=400,
                    fields={f"{role}_model": NOT_ENABLED},
                )
            picked[role] = model.name
        before = chosen_names()
        changes = {
            f"{role}_model": {"old": before[role], "new": name}
            for role, name in picked.items()
            if before[role] != name
        }
        if not changes:
            raise AppError("nothing_changed", CHANGE_NOTHING, status_code=400)
        for role, name in picked.items():
            _choose(role, name)
        record("admin.models_selected", actor=admin, reason=reason, changes=changes)
    return chosen_names()
