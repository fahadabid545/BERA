"""Keeps the security suite itself whole: every area exists, is marked and is not empty."""

import ast
from pathlib import Path

import pytest

from core.tests.security_suite import AREAS, SECURITY_TEST_FILES

SERVER_ROOT = Path(__file__).resolve().parents[2]


def names_of_tests(path):
    tree = ast.parse((SERVER_ROOT / path).read_text())
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


# The areas the ticket names. Removing one from the suite must be a deliberate change here.
REQUIRED_AREAS = [
    "sign-in",
    "tokens: tampered, expired, reused, wrong audience",
    "permissions per role",
    "wrong-company access for every kind of object",
    "hostile input",
    "rate limits",
    "blocked and suspended users",
]


@pytest.mark.parametrize("area", REQUIRED_AREAS)
def test_every_area_the_ticket_names_is_in_the_suite(area):
    assert area in AREAS


@pytest.mark.parametrize("path", sorted(SECURITY_TEST_FILES))
def test_every_file_of_the_suite_exists_and_holds_tests(path):
    assert (SERVER_ROOT / path).is_file(), f"{path} is listed in the security suite but missing"
    assert names_of_tests(path), f"{path} is listed in the security suite but has no tests"


def test_the_suite_is_marked_so_it_can_run_alone(request):
    inside = [
        item for item in request.session.items if Path(item.fspath).is_relative_to(SERVER_ROOT)
    ]

    def name(item):
        return Path(item.fspath).relative_to(SERVER_ROOT).as_posix()

    marked = {name(item) for item in inside if item.get_closest_marker("security")}
    # Under a partial run (one file) only the collected files can be marked.
    assert marked == SECURITY_TEST_FILES & {name(item) for item in inside}
