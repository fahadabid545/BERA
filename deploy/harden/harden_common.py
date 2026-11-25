"""Shared by the server hardening scripts. Each script prints exactly what it will change
before it changes anything, and every one has a dry-run mode that stops after printing."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class HardeningError(Exception):
    """Stopped on purpose; the message says what is wrong and never holds a secret value."""


def show_change(title, text):
    print(f"--- {title}")
    print(text.rstrip() or "(nothing)")
    print("---")


def write_file(path, text, *, mode=0o644, dry_run=False, quiet=False):
    """Writes through a temporary file in the same folder, so a reader never sees half a file."""
    path = Path(path)
    if quiet:
        print(f"writing {path}")
    else:
        show_change(f"{'would write' if dry_run else 'writing'} {path}", text)
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def remove_file(path, *, dry_run=False):
    path = Path(path)
    print(f"{'would remove' if dry_run else 'removing'} {path}")
    if not dry_run:
        path.unlink(missing_ok=True)


def run(command, *, dry_run=False, input_text=None, check=True):
    """Runs a program (never through a shell). In dry-run mode it only prints the command."""
    print(f"{'would run' if dry_run else 'running'}: {' '.join(command)}")
    if dry_run:
        return None
    return subprocess.run(command, input=input_text, text=True, capture_output=True, check=check)


def require_root():
    if os.geteuid() != 0:
        raise HardeningError("This must run as root (use sudo), or with --dry-run.")


def main_wrapper(function):
    """Turns a HardeningError into a one-line message and a non-zero exit status."""
    try:
        return function()
    except HardeningError as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        return 1
