"""Compares the staging and production environment files and fails if they share anything.

    python scripts/check_environments.py /etc/bera/staging.env /etc/bera/production.env

Prints setting names only, never a value.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from config.separation import compare  # noqa: E402


def read_env_file(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip().strip("'\"")
    return values


def main(argv):
    if len(argv) != 3:
        print("Usage: check_environments.py STAGING_ENV_FILE PRODUCTION_ENV_FILE")
        return 2
    problems = compare(read_env_file(argv[1]), read_env_file(argv[2]))
    for problem in problems:
        print(f"SHARED: {problem}")
    print("Staging and production are separate." if not problems else "Not separate.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
