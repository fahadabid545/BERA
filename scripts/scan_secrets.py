"""Looks for keys, passwords and tokens in the files the project tracks.

    python scripts/scan_secrets.py           scan every tracked file (what CI runs)
    python scripts/scan_secrets.py FILE...   scan only these files

Exits with a failure if anything looks like a real secret. Fake values written for tests
and examples are fine when the line says so ("fake", "example", "test-only") or ends with
a "nosecret" comment. The matching text is never printed, only the file, line and kind.
"""

import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NO_SECRET_MARKERS = ("nosecret", "fake", "example", "test-only", "placeholder", "your-")
# Files that are mostly long hashes or generated, never hand-written secrets.
SKIPPED_NAMES = {"package-lock.json", "tsconfig.tsbuildinfo"}
MIN_GENERIC_LENGTH = 24
MIN_GENERIC_ENTROPY = 3.5

KNOWN_FORMATS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Stripe key": re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    "Stripe webhook secret": re.compile(r"\bwhsec_[A-Za-z0-9]{16,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "signed token": re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"),
    "database address with password": re.compile(r"\bpostgres(?:ql)?://[^:/\s@]+:[^@\s]+@"),
}
GENERIC_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?:secret|token|passw(?:or)?d|api[_-]?key|private[_-]?key|credential)\w*
    ["']?\s*[:=]\s*["']([A-Za-z0-9+/=_\-]{LENGTH,})["']
    """.replace("LENGTH", str(MIN_GENERIC_LENGTH))
)


def entropy(text):
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def findings_in_line(line):
    if any(marker in line.lower() for marker in NO_SECRET_MARKERS):
        return []
    found = [kind for kind, pattern in KNOWN_FORMATS.items() if pattern.search(line)]
    for match in GENERIC_ASSIGNMENT.finditer(line):
        if entropy(match.group(1)) >= MIN_GENERIC_ENTROPY:
            found.append("secret-looking value assigned to a secret-like name")
    return found


def scan_text(text):
    """[(line number, kind)] for every suspicious line."""
    return [
        (number, kind)
        for number, line in enumerate(text.splitlines(), 1)
        for kind in findings_in_line(line)
    ]


def tracked_files():
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / name for name in listing.decode().split("\0") if name]


def shown(path):
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path.name


def misplaced_env_files(paths):
    """Local environment files hold real secrets and must never be tracked."""
    return [path for path in paths if path.name.startswith(".env") and path.name != ".env.example"]


def scan(paths):
    problems = [
        f"{shown(path)}: environment file is tracked" for path in misplaced_env_files(paths)
    ]
    for path in paths:
        if path.name in SKIPPED_NAMES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # images and other binary files
        for number, kind in scan_text(text):
            problems.append(f"{shown(path)}:{number}: looks like a {kind}")
    return problems


def main(arguments):
    paths = [Path(argument).resolve() for argument in arguments] or tracked_files()
    problems = scan(paths)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} possible secret(s) found. Remove them and replace the real value.")
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
