"""Checks that staging and production share nothing.

Given the two environment files' values, it reports every secret, database, bucket, port and
address that is the same in both. Secrets are compared by their SHA-256 hash and nothing it
returns or prints holds a value: only setting names. Used by `scripts/check_environments.py` and
by the deploy script before it touches anything.
"""

import hashlib
import re
from urllib.parse import urlsplit

# Anything named like a secret is compared, so a new secret is covered without editing this file.
SECRET_NAME = re.compile(r"SECRET|KEY|PASSWORD|TOKEN")
PORTS = ("API_PORT", "WEB_PORT")
LIST_SETTINGS = ("ALLOWED_HOSTS", "ALLOWED_ORIGINS")  # comma separated
SINGLE_ADDRESSES = ("WEB_BASE_URL", "NEXT_PUBLIC_SITE_URL")
DATABASE_URLS = (
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "BACKUP_DATABASE_URL",
    "RESTORE_TEST_DATABASE_URL",
)
BUCKETS = (
    "R2_BUCKET",
    "BACKUP_R2_BUCKET",
    "STAGING_EMAIL_FOLDER",
    "PRIVATE_FILES_ROOT",
)  # storage places


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _parts(url):
    """The password, the account and the database a database address points at."""
    try:
        split = urlsplit(url)
        if not split.hostname:  # nothing set: nothing to compare
            return "", "", ""
        return (
            split.password or "",
            split.username or "",
            f"{split.hostname}:{split.port}{split.path}",
        )
    except ValueError:
        return "", "", ""


def _items(value):
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


def _same(first, second):
    return bool(first) and first == second


def compare(staging, production):
    """Problems as plain sentences naming settings, never values. Empty means separate."""
    problems = []

    def both_have(name):
        return staging.get(name, "").strip(), production.get(name, "").strip()

    for name in sorted(set(staging) | set(production)):
        if SECRET_NAME.search(name) and name not in DATABASE_URLS:
            one, two = both_have(name)
            if one and _hash(one) == _hash(two):
                problems.append(f"{name} is the same secret in both environments.")
    for name in DATABASE_URLS:
        one, two = (_parts(value) for value in both_have(name))
        if _same(_hash(one[0]) if one[0] else "", _hash(two[0]) if two[0] else ""):
            problems.append(f"{name} has the same database password in both environments.")
        if _same(one[1], two[1]):
            problems.append(f"{name} uses the same database account in both environments.")
        if _same(one[2], two[2]):
            problems.append(f"{name} points at the same database in both environments.")
    for name in PORTS + BUCKETS + SINGLE_ADDRESSES:
        one, two = both_have(name)
        if _same(one.rstrip("/"), two.rstrip("/")):
            problems.append(f"{name} is the same in both environments.")
    for name in LIST_SETTINGS:
        one, two = both_have(name)
        if _items(one) & _items(two):
            problems.append(f"{name} shares an address with the other environment.")
    for name in ("DATABASE_URL", "WEB_BASE_URL", "API_PORT", "WEB_PORT", "R2_BUCKET"):
        for label, values in (("staging", staging), ("production", production)):
            if not values.get(name, "").strip():
                problems.append(f"{name} is missing in {label}.")
    return problems
