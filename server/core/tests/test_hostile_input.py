import json
import re
from pathlib import Path

import pytest

from core.validation import safe_file_name

pytestmark = [pytest.mark.urls("core.tests.urls_for_input"), pytest.mark.django_db]

VALID = {"title": "Backend engineer", "stage": "new"}


def post(client, body, **extra):
    return client.post("/api/projects/", json.dumps(body), content_type="application/json", **extra)


def fields_of(response):
    return response.json()["error"]["fields"]


def test_valid_input_is_accepted(client):
    response = post(client, {**VALID, "notes": "Line one\nLine two", "count": 5})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "extra",
    [{"is_admin": True}, {"company_id": 2}, {"<script>alert(1)</script>": "x"}, {"x" * 5000: 1}],
    ids=["admin flag", "other company", "script name", "huge name"],
)
def test_unknown_extra_fields_are_refused_by_name(client, extra):
    response = post(client, {**VALID, **extra})
    assert response.status_code == 400
    (name,) = fields_of(response)
    assert name == next(iter(extra))[:64]
    assert fields_of(response)[name] == "This field is not allowed."


@pytest.mark.parametrize(
    "title",
    [123, True, ["a"], {"a": 1}, None, "", "   ", "x" * 201, "bad\x00name", "tab\there", "a\nb"],
    ids=[
        "number",
        "bool",
        "list",
        "object",
        "null",
        "empty",
        "spaces",
        "too long",
        "NUL",
        "tab",
        "newline",
    ],
)
def test_a_title_must_be_single_line_text_of_the_right_length(client, title):
    response = post(client, {**VALID, "title": title})
    assert response.status_code == 400
    assert list(fields_of(response)) == ["title"]


@pytest.mark.parametrize("stage", ["", "NEW", "approved' OR '1'='1", 7, None])
def test_choices_accept_only_the_allowed_values(client, stage):
    response = post(client, {**VALID, "stage": stage})
    assert response.status_code == 400
    assert list(fields_of(response)) == ["stage"]


@pytest.mark.parametrize("count", [0, 101, -1, "5; DROP TABLE x", 1.5, 10**30])
def test_numbers_must_be_whole_and_in_range(client, count):
    response = post(client, {**VALID, "count": count})
    assert response.status_code == 400
    assert list(fields_of(response)) == ["count"]


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "'; DROP TABLE companies; --",
        "x' OR '1'='1",
        "%' UNION SELECT password FROM auth_user --",
        "\u202egnp.exe",
        "emoji \U0001f600 and Ünïcödé",
    ],
)
def test_hostile_text_is_stored_as_plain_text_and_harmless_to_the_database(client, hostile):
    response = post(client, {**VALID, "title": hostile, "notes": hostile})
    assert response.status_code == 200
    assert response.json()["title"] == hostile  # kept exactly, never run
    assert response.json()["matches"] == 0
    assert response["Content-Type"].startswith("application/json")
    assert response["X-Content-Type-Options"] == "nosniff"
    # The tables are still there.
    from companies.models import Company

    assert Company.objects.count() == 0


def test_text_is_normalised_to_one_unicode_form(client):
    response = post(client, {**VALID, "title": "Cafe\u0301"})
    assert response.json()["title"] == "Caf\u00e9"


@pytest.mark.parametrize("body", [b"{", b"[1, 2", b"not json", b"\xff\xfe"])
def test_broken_bodies_get_a_plain_message(client, body):
    response = client.post("/api/projects/", body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "The request could not be read."


def test_a_body_that_is_not_an_object_is_refused(client):
    assert post(client, ["a"]).status_code == 400


def test_error_messages_name_the_field_and_hide_internals(client):
    response = post(client, {"title": "x" * 500, "stage": "?"})
    text = response.content.decode()
    assert set(fields_of(response)) == {"title", "stage"}
    for internal in ("Traceback", "SELECT", ".py", "serializer", "Serializer", "psycopg"):
        assert internal not in text


@pytest.mark.parametrize(
    ("hostile", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\config", "config"),
        ("/etc/shadow", "shadow"),
        ("C:\\Users\\x\\cv.pdf", "cv.pdf"),
        ("....//....//secret.pdf", "secret.pdf"),
        ("..", "file"),
        (".", "file"),
        ("", "file"),
        (".env", "env"),
        ("cv.pdf\x00.exe", "cv.pdf.exe"),
        ("name<with>bad:chars?.pdf", "name_with_bad_chars_.pdf"),
        ("CON.pdf", "_CON.pdf"),
        ("  spaced name.pdf  ", "spaced name.pdf"),
        ("%2e%2e%2fsecret.pdf", "%2e%2e%2fsecret.pdf"),
    ],
)
def test_file_names_never_point_to_other_folders(hostile, expected):
    cleaned = safe_file_name(hostile)
    assert cleaned == expected
    assert not any(bad in cleaned for bad in ("/", "\\", ".."))


def test_very_long_file_names_are_shortened_but_keep_their_ending():
    cleaned = safe_file_name("a" * 5000 + ".pdf")
    assert len(cleaned) == 150
    assert cleaned.endswith(".pdf")


@pytest.mark.parametrize("path", ["../../etc/passwd", "a/b.pdf"])
def test_file_name_field_in_a_request_comes_out_clean(client, path):
    response = post(client, {**VALID, "file_name": path})
    assert "/" not in response.json()["file_name"]


def test_form_requests_over_the_size_limit_are_refused(client):
    huge = json.dumps({**VALID, "notes": "x" * (300 * 1024)})
    response = client.post("/api/projects/", huge, content_type="application/json")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_a_body_of_unknown_length_is_refused(client):
    response = client.post(
        "/api/projects/", "{}", content_type="application/json", HTTP_TRANSFER_ENCODING="chunked"
    )
    assert response.status_code == 411


def test_a_form_just_under_the_limit_is_read(client):
    body = json.dumps({**VALID, "notes": "x" * 2000})
    response = client.post("/api/projects/", body, content_type="application/json")
    assert response.status_code == 200


def test_upload_routes_may_be_larger_than_forms(monkeypatch):
    from core import middleware

    monkeypatch.setattr(middleware, "UPLOAD_ROUTE_PREFIXES", ("/api/uploads/",))
    form_limit = middleware.largest_allowed_request_bytes("/api/projects/")
    assert middleware.largest_allowed_request_bytes("/api/uploads/cv/") > form_limit


SERVER = Path(__file__).resolve().parents[2]
RAW_SQL_PATTERNS = [
    re.compile(r"\.raw\("),
    re.compile(r"\.extra\("),
    re.compile(r"\bRawSQL\b"),
    re.compile(r"\.execute\(\s*f[\"']"),
    re.compile(r"\.execute\([^)]*(%|\.format\(|\+)"),
]


def test_no_query_is_built_by_joining_raw_input():
    offenders = []
    for source in SERVER.rglob("*.py"):
        parts = source.relative_to(SERVER).parts
        if ".venv" in parts or "migrations" in parts or "tests" in parts:
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern.search(line) for pattern in RAW_SQL_PATTERNS):
                offenders.append(f"{'/'.join(parts)}:{number}")
    assert offenders == []
