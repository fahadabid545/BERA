"""What a super admin can read and change of the platform settings, from the admin panel.

Every change is audited with who, when, and the old and new value (never a secret's value), and
applies at once: `PlatformSetting` saves clear the settings cache (see service.py). A value equal
to its default is stored as no override, so "reset to default" and "set to the default" are the
same state. Settings that have their own screen, with their own rules and reasons, are not edited
here (`MANAGED_ELSEWHERE`)."""

import json

from django.db import transaction

from adminusers.models import AdminUser
from audit.service import record
from core.errors import form_error, not_found

from .definitions import DEFINITIONS
from .models import PlatformSetting
from .service import clear_cache

# Edited on their own screens: the models and prompts (AI), the spend alerts and the playground
# budget (AI controls), the PKR rate (Cost vs revenue) and maintenance mode (Maintenance).
MANAGED_ELSEWHERE = frozenset(
    {
        "ai.reading_model",
        "ai.scoring_model",
        "ai.reading_prompt_version",
        "ai.scoring_prompt_version",
        "ai.daily_spend_alert_usd",
        "ai.monthly_spend_alert_usd",
        "ai.playground_monthly_budget_usd",
        "billing.pkr_per_usd",
        "maintenance.enabled",
        "maintenance.message",
    }
)
# A setting whose value must never reach the audit log: only the fact that it changed is kept.
SECRET_STYLE = frozenset()

# The curated pages. "All values" lists everything editable.
PAGES = {
    "general": ["general.app_name", "general.support_email"],
    "limits": [
        "uploads.max_file_size_mb",
        "uploads.max_files_per_batch",
        "tokens.team_invite_days",
        "team.max_accounts_per_company",
    ],
    "rate_limits": sorted(key for key in DEFINITIONS if key.startswith("rate_limits.")),
    "security": [
        "tokens.access_minutes",
        "tokens.refresh_days",
        "tokens.admin_access_minutes",
        "tokens.admin_refresh_hours",
        "passwords.min_length",
        "passwords.max_length",
        "passwords.block_common_passwords",
    ],
}
NOT_ALLOWED = "This value is not allowed."
MAX_AUDIT_LENGTH = 200


def editable_keys():
    return sorted(key for key in DEFINITIONS if key not in MANAGED_ELSEWHERE)


def _stored():
    return dict(PlatformSetting.objects.values_list("key", "value"))


def _kind(default):
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, list):
        return "list"
    if isinstance(default, (int, float)) or default is None:
        return "number"
    return "text"


def _item(key, stored):
    default = DEFINITIONS[key].default
    value = stored.get(key, default)
    if not DEFINITIONS[key].is_valid(value):
        value = default
    return {
        "key": key,
        "group": key.split(".")[0],
        "kind": _kind(default),
        "value": value,
        "default": default,
        "is_default": value == default,
    }


def list_settings(page=None):
    if page is not None and page not in PAGES:
        raise not_found()
    stored = _stored()
    keys = PAGES[page] if page else editable_keys()
    body = {"items": [_item(key, stored) for key in keys]}
    if page == "security":
        body["admin_two_step"] = _admin_two_step()
    return body


def _admin_two_step():
    """Shown on the Security page. Every admin must use two-step verification: the rule is always
    on and has no setting, so this only reports it and how far admins have come."""
    active = AdminUser.objects.filter(status=AdminUser.Status.ACTIVE)
    return {
        "required": True,
        "set_up": active.filter(two_step_enabled=True).count(),
        "not_set_up": active.filter(two_step_enabled=False).count(),
    }


def _audit_value(value):
    """A value as the audit log can hold it: short plain text, a number or a yes or no."""
    if value is None or isinstance(value, (bool, int)):
        return value
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= MAX_AUDIT_LENGTH else text[: MAX_AUDIT_LENGTH - 1] + "…"


def _changes_for(key, old, new):
    if key in SECRET_STYLE:
        return None
    return {"value": {"old": _audit_value(old), "new": _audit_value(new)}}


def _check_together(values):
    """Rules between two settings that one setting's own range cannot see."""
    problems = {}
    if values["passwords.min_length"] > values["passwords.max_length"]:
        problems["passwords.min_length"] = (
            "The shortest password cannot be longer than the longest."
        )
    return problems


def _write(key, value):
    if value == DEFINITIONS[key].default:
        PlatformSetting.objects.filter(key=key).delete()
    else:
        PlatformSetting.objects.update_or_create(key=key, defaults={"value": value})


def update_settings(admin, new_values):
    """Saves several settings at once, all or none. Returns the keys that really changed."""
    problems = {}
    editable = set(editable_keys())
    for key, value in new_values.items():
        if key not in editable:
            problems[key] = NOT_ALLOWED
        elif not DEFINITIONS[key].is_valid(value):
            problems[key] = NOT_ALLOWED
    if problems:
        raise form_error(problems)
    changed = []
    with transaction.atomic():
        stored = _stored()
        current = {key: _item(key, stored)["value"] for key in DEFINITIONS}
        after = {**current, **new_values}
        if problems := _check_together(after):
            raise form_error(problems)
        for key, value in new_values.items():
            if value == current[key]:
                continue
            _write(key, value)
            changed.append(key)
            record(
                "admin.setting_changed",
                actor=admin,
                details={"setting": key},
                changes=_changes_for(key, current[key], value),
            )
    clear_cache()
    return changed


def reset_setting(admin, key):
    if key not in editable_keys():
        raise not_found()
    with transaction.atomic():
        stored = _stored()
        if key not in stored:
            return False
        old = _item(key, stored)["value"]
        PlatformSetting.objects.filter(key=key).delete()
        record(
            "admin.setting_reset",
            actor=admin,
            details={"setting": key},
            changes=_changes_for(key, old, DEFINITIONS[key].default),
        )
    clear_cache()
    return True


def maintenance_state():
    stored = _stored()
    return {
        "enabled": _item("maintenance.enabled", stored)["value"],
        "message": _item("maintenance.message", stored)["value"],
    }


def set_maintenance(admin, *, enabled, message, reason):
    """Turns maintenance mode on or off and sets what companies are told. The reason is needed
    because it affects every company at once."""
    if enabled and not DEFINITIONS["maintenance.message"].is_valid(message):
        raise form_error({"message": "Write the message companies will see."})
    with transaction.atomic():
        before = maintenance_state()
        after = {"enabled": enabled, "message": message or before["message"]}
        if after["message"] != before["message"] and not DEFINITIONS[
            "maintenance.message"
        ].is_valid(after["message"]):
            raise form_error({"message": "This message is not allowed."})
        if after == before:
            return before
        _write("maintenance.enabled", after["enabled"])
        _write("maintenance.message", after["message"])
        record(
            "admin.maintenance_changed",
            actor=admin,
            reason=reason,
            details={"message_changed": after["message"] != before["message"]},
            changes={"enabled": {"old": before["enabled"], "new": after["enabled"]}},
        )
    clear_cache()
    return after
