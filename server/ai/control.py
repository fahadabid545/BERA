"""AI outage handling: keeping the system calm when the AI provider fails.

Failed calls are tried again by the processing pipeline (`cvs/processing.py`: up to the platform's
number of tries, with waits). On top of that, AI work can be paused for everyone:

- automatically, when `ai.pause_after_failures` calls fail in a row. It lasts
  `ai.auto_pause_minutes` and then ends by itself (`end_expired_pause`, run by the once-a-minute
  sweep). Counting starts again after it, so the failures that caused it do not pause it twice;
- by hand, with the super admin's switch (`pause`, `resume`), which is audited and needs a reason.

While paused, no CV is picked up and nobody's attempts are used up: waiting CVs stay waiting, in
their order, and carry on when AI work resumes. Users see `PAUSED_MESSAGE`. When a pause ends the
CVs that failed only because of the provider are put back in line (`register_resume_hook`).
Nothing here reads or stores CV text.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from audit.service import record
from platform_settings.service import get_setting

from .models import AiCall, AiControl

logger = logging.getLogger(__name__)

PAUSED_MESSAGE = "AI scoring is paused. We will resume automatically."
_RESUME_HOOKS = []


def register_resume_hook(hook):
    """`hook()` runs when AI work resumes (by hand or after an automatic pause)."""
    if hook not in _RESUME_HOOKS:
        _RESUME_HOOKS.append(hook)


def _row(lock=False):
    AiControl.objects.get_or_create(pk=1)
    rows = AiControl.objects.select_for_update() if lock else AiControl.objects
    return rows.get(pk=1)


def _automatic(row, now):
    return row.auto_paused_until is not None and now < row.auto_paused_until


def is_paused(now=None):
    """True while AI work must not run, for either reason."""
    row = _row()
    return row.paused or _automatic(row, now or timezone.now())


def describe(now=None):
    now = now or timezone.now()
    row = _row()
    automatic = _automatic(row, now)
    return {
        "paused": row.paused or automatic,
        "paused_by_admin": row.paused,
        "paused_automatically": automatic,
        "resumes_at": row.auto_paused_until if automatic else None,
        "message": PAUSED_MESSAGE if row.paused or automatic else "",
    }


def _failures_in_a_row(row):
    """Failed calls since the last good call (or since counting was reset)."""
    since = row.counting_from
    last_good = (
        AiCall.objects.filter(result=AiCall.Result.OK).order_by("-created_at").values("created_at")
    ).first()
    if last_good and (since is None or last_good["created_at"] > since):
        since = last_good["created_at"]
    failed = AiCall.objects.filter(result=AiCall.Result.FAILED)
    return (failed.filter(created_at__gt=since) if since else failed).count()


def note_failure(now=None):
    """Called after a failed AI call: pauses AI work when too many have failed in a row."""
    now = now or timezone.now()
    with transaction.atomic():
        row = _row(lock=True)
        if row.paused or _automatic(row, now):
            return False
        if _failures_in_a_row(row) < get_setting("ai.pause_after_failures"):
            return False
        until = now + timedelta(minutes=get_setting("ai.auto_pause_minutes"))
        row.auto_paused_at, row.auto_paused_until, row.counting_from = now, until, until
        row.save(update_fields=["auto_paused_at", "auto_paused_until", "counting_from"])
    logger.warning("AI work was paused automatically after repeated failures.")
    return True


def _run_resume_hooks():
    for hook in _RESUME_HOOKS:
        hook()


def end_expired_pause(now=None):
    """Once a minute: ends an automatic pause whose time is up and puts provider failures back
    in line. Returns whether a pause ended."""
    now = now or timezone.now()
    with transaction.atomic():
        row = _row(lock=True)
        if row.auto_paused_until is None or now < row.auto_paused_until:
            return False
        row.auto_paused_until = None
        row.save(update_fields=["auto_paused_until"])
    logger.info("AI work resumed after the automatic pause.")
    _run_resume_hooks()
    return True


def pause(admin, reason):
    """The super admin's switch: stops all AI work at once."""
    with transaction.atomic():
        row = _row(lock=True)
        row.paused, row.paused_changed_at = True, timezone.now()
        row.save(update_fields=["paused", "paused_changed_at"])
        record("admin.ai_paused", actor=admin, reason=reason)
    return describe()


def resume(admin, reason):
    """The super admin's switch: lets AI work run again (ending an automatic pause too), and
    puts waiting work back in motion in order."""
    now = timezone.now()
    with transaction.atomic():
        row = _row(lock=True)
        row.paused, row.paused_changed_at = False, now
        row.auto_paused_until, row.counting_from = None, now
        row.save(
            update_fields=["paused", "paused_changed_at", "auto_paused_until", "counting_from"]
        )
        record("admin.ai_resumed", actor=admin, reason=reason)
    _run_resume_hooks()
    return describe()
