"""Read platform settings with `get_setting("group.name")`.

Values are read at the moment of use, so a change applies to new activity
without a restart. Callers that need a value to stay fixed for a past record
must store it on that record; changing a setting never rewrites old records.

Reading never crashes: a stored value that is invalid or unknown is ignored in
favour of the default, and an unreachable database falls back to the last good
values (or the defaults if there are none yet).
"""

import copy
import logging
import threading
import time

from django.db import DatabaseError
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.errors import AppError

from .definitions import DEFINITIONS
from .models import PlatformSetting

logger = logging.getLogger(__name__)

CACHE_SECONDS = 30
WARNING_INTERVAL_SECONDS = 3600
DATABASE_WARNING_LABEL = "database"

_lock = threading.Lock()
_values = None  # last known good values for every setting
_loaded_at = 0.0
_last_warned_at = {}


def _now():
    return time.monotonic()


def get_setting(key):
    if key not in DEFINITIONS:
        raise AppError("unknown_setting", f"There is no platform setting named '{key}'.", None, 500)
    with _lock:
        if _values is None or _now() - _loaded_at >= CACHE_SECONDS:
            _reload()
        return copy.deepcopy(_values[key])


def clear_cache(**_signal_arguments):
    """Make the next read look at the database again. Called when an admin saves."""
    global _loaded_at
    with _lock:
        _loaded_at = float("-inf")


def _read_overrides():
    return list(PlatformSetting.objects.values_list("key", "value"))


def _reload():
    global _values, _loaded_at
    try:
        overrides = _read_overrides()
    except DatabaseError:
        _warn(
            DATABASE_WARNING_LABEL, "Platform settings could not be read; using last known values."
        )
        if _values is None:
            _values = _defaults()
        _loaded_at = _now()
        return
    values = _defaults()
    for key, value in overrides:
        definition = DEFINITIONS.get(key)
        if definition is None:
            _warn(key, f"Ignoring stored setting '{key}': there is no such setting.")
        elif not definition.is_valid(value):
            _warn(key, f"Ignoring stored setting '{key}': its value is not allowed. Using default.")
        else:
            values[key] = value
    _values = values
    _loaded_at = _now()


def _defaults():
    return {key: copy.deepcopy(definition.default) for key, definition in DEFINITIONS.items()}


def _warn(label, message):
    """At most one warning per setting per hour. Never includes the stored value."""
    last = _last_warned_at.get(label)
    if last is None or _now() - last >= WARNING_INTERVAL_SECONDS:
        _last_warned_at[label] = _now()
        logger.warning(message)


receiver(post_save, sender=PlatformSetting)(clear_cache)
receiver(post_delete, sender=PlatformSetting)(clear_cache)
