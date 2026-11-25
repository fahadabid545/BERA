"""What one line of the launch check says. Every item ends as exactly one of three words, and
a part that could not be checked is never counted as passing."""

from dataclasses import dataclass

OK = "OK"
NOT_OK = "NOT OK"
OWNER = "owner must confirm"


@dataclass(frozen=True)
class Item:
    number: int
    title: str
    status: str
    notes: tuple[str, ...]


def ok(text):
    return OK, text


def not_ok(text):
    return NOT_OK, text


def owner(text):
    return OWNER, text


def item(number, title, parts):
    """One item from its parts: NOT OK when any part failed, otherwise "owner must confirm" when
    any part needs the owner, otherwise OK. Notes name what failed or what the owner must do;
    a passing part adds none."""
    statuses = {status for status, _ in parts}
    status = NOT_OK if NOT_OK in statuses else OWNER if OWNER in statuses else OK
    notes = tuple(text for part_status, text in parts if part_status != OK)
    return Item(number, title, status, notes)
