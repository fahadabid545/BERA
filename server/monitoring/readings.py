"""What the server's disk and memory look like, as percentages. Linux only; where a reading is
not available (a developer's computer) it is None and the check is skipped."""

import shutil
from pathlib import Path

from django.conf import settings

MEMORY_FILE = Path("/proc/meminfo")


def disk_used_percent(paths=None):
    """The fullest of the watched places, as `df` shows it (space kept for the system counts)."""
    watched = paths or ["/", str(settings.BASE_DIR)]
    percents = []
    for path in watched:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        in_use = usage.total - usage.free
        percents.append(100 * in_use / usage.total if usage.total else 0)
    return round(max(percents), 1) if percents else None


def memory_used_percent(meminfo=MEMORY_FILE):
    """Memory in use by what cannot be given back, from `MemAvailable`: the kernel's own estimate of
    what a program can still get, counting cache that is released on demand. Not the "free" figure,
    which looks alarming on any healthy server because the cache uses the rest."""
    try:
        lines = Path(meminfo).read_text().splitlines()
        values = {
            line.split(":")[0]: int(line.split(":")[1].split()[0]) for line in lines if ":" in line
        }
        total, available = values["MemTotal"], values["MemAvailable"]
    except (OSError, KeyError, ValueError, IndexError):
        return None
    return round(100 * (total - available) / total, 1) if total else None
