"""Jobs that run on a schedule. The schedules themselves are created by migrations (`core` for
the daily clean-up, `cvs` for the once-a-minute processing sweep), so every deployment has them."""

from . import rate_limits
from .jobs import logged_job


@logged_job
def purge_rate_limit_counters():
    """Clears finished rate limit windows and ended blocks; scheduled once a day."""
    rate_limits.purge_old_counters()
