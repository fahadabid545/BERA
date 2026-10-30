"""Limits on how often something may be done, kept in PostgreSQL so every server process
and every restart counts the same way.

Counts are per fixed time window and per source (an address, an account, an email or a
company), so one source's heavy use never changes another's. Sources that keep hitting a
limit are blocked for a while. Sources are stored only as hashes.
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from platform_settings.service import get_setting

from .models import BlockedSource, RateCounter

SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class Rule:
    name: str
    setting_key: str
    window_seconds: int


LOGIN = Rule("login", "rate_limits.login_per_minute", 60)
REFRESH = Rule("refresh", "rate_limits.refresh_per_minute", 60)
SIGN_UP = Rule("sign_up", "rate_limits.sign_up_per_hour", 3600)
RESEND_VERIFICATION = Rule("resend_verification", "rate_limits.verification_resend_per_hour", 3600)
SIGN_UP_NOTICE = Rule("sign_up_notice", "rate_limits.sign_up_notices_per_hour", 3600)
PASSWORD_RESET = Rule("password_reset", "rate_limits.password_reset_per_hour", 3600)
INVITES = Rule("invites", "rate_limits.invites_per_hour", 3600)
UPLOADS = Rule("uploads", "rate_limits.upload_files_per_10_minutes", 600)
DOWNLOADS = Rule("downloads", "rate_limits.downloads_per_minute", 60)
CONTACT = Rule("contact", "rate_limits.contact_per_hour", 3600)
OTHER_REQUESTS = Rule("other_requests", "rate_limits.other_requests_per_minute", 60)
VIOLATIONS = "violations"


def now():
    return timezone.now()


def _digest(*parts):
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def try_again_message(wait_seconds):
    minutes = max(1, math.ceil(wait_seconds / SECONDS_PER_MINUTE))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many attempts. Try again in {minutes} {unit}."


def _add_to_counter(key, window_seconds, cost):
    """Add to this window's count and return the new total, safely when requests overlap."""
    window_start = int(now().timestamp() // window_seconds) * window_seconds
    counters = RateCounter.objects.filter(key=key, window_start=window_start)
    while not counters.update(count=F("count") + cost):
        try:
            RateCounter.objects.create(key=key, window_start=window_start, count=cost)
            return cost, window_start
        except IntegrityError:
            continue  # another request created it first; add to theirs
    return counters.values_list("count", flat=True).get(), window_start


def seconds_blocked(subject):
    """How long the source stays blocked, or 0."""
    blocked = BlockedSource.objects.filter(key=_digest("block", subject)).first()
    if blocked is None:
        return 0
    remaining = (blocked.blocked_until - now()).total_seconds()
    return max(0, math.ceil(remaining))


def _record_violation(subject):
    window = get_setting("rate_limits.violation_window_minutes") * SECONDS_PER_MINUTE
    total, _ = _add_to_counter(_digest(VIOLATIONS, subject), window, 1)
    if total < get_setting("rate_limits.violations_before_block"):
        return 0
    block_seconds = get_setting("rate_limits.block_minutes") * SECONDS_PER_MINUTE
    BlockedSource.objects.update_or_create(
        key=_digest("block", subject),
        defaults={"blocked_until": now() + timedelta(seconds=block_seconds)},
    )
    return block_seconds


def hit(rule, subject, cost=1):
    """Count one use. Returns 0 when allowed, otherwise how many seconds to wait."""
    blocked = seconds_blocked(subject)
    if blocked:
        return blocked
    total, window_start = _add_to_counter(_digest(rule.name, subject), rule.window_seconds, cost)
    if total <= get_setting(rule.setting_key):
        return 0
    blocked = _record_violation(subject)
    if blocked:
        return blocked
    return max(1, window_start + rule.window_seconds - int(now().timestamp()))


def purge_old_counters():
    """Removes finished windows and ended blocks; for a periodic job."""
    longest_window = max(rule.window_seconds for rule in ALL_RULES)
    longest_window = max(
        longest_window, get_setting("rate_limits.violation_window_minutes") * SECONDS_PER_MINUTE
    )
    cutoff = int(now().timestamp()) - longest_window
    RateCounter.objects.filter(window_start__lt=cutoff).delete()
    BlockedSource.objects.filter(blocked_until__lt=now()).delete()


ALL_RULES = (
    LOGIN,
    REFRESH,
    SIGN_UP,
    SIGN_UP_NOTICE,
    RESEND_VERIFICATION,
    PASSWORD_RESET,
    INVITES,
    UPLOADS,
    DOWNLOADS,
    CONTACT,
    OTHER_REQUESTS,
)
