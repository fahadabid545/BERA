import logging

import pytest

from core import request_context
from core.logging_setup import REDACTED, redact

logger = logging.getLogger("core.tests")


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("login password=hunter2 failed", "hunter2"),
        ('body {"password": "a long pass phrase"}', "pass phrase"),
        ("body {'token': 'tok en'}", "tok en"),
        ("Authorization: Bearer abc.def-ghi", "abc.def-ghi"),
        ("sent eyJhbGciOi.eyJzdWIiOjF9.c2lnbmF0dXJl here", "eyJhbGciOi"),
        ('"POST /verify/?token=abc123&next=/home HTTP/1.1" 200', "abc123"),
        ("response access_token: abc123", "abc123"),
        ("cookie=sessionid-xyz", "sessionid-xyz"),
        ("api_key=sk-live-123", "sk-live-123"),
        ("user jane.doe@example.com signed in", "jane.doe@example.com"),
    ],
)
def test_redact_removes_secrets_and_personal_details(text, secret):
    assert secret not in redact(text)


def test_redact_keeps_the_rest_of_the_line_readable():
    redacted = redact('"POST /verify/?token=abc123&next=/home HTTP/1.1" 200')
    assert redacted == f'"POST /verify/?token={REDACTED}&next=/home HTTP/1.1" 200'


def test_redact_leaves_ordinary_messages_alone():
    text = "Job 12 finished in 3 seconds for company 7"
    assert redact(text) == text


def test_log_lines_have_time_request_user_company_and_the_problem(project_log):
    token = request_context.start()
    try:
        request_context.bind_actor(user_id=7, company_id=3)
        reference = request_context.current_reference()
        logger.warning("Quota exceeded")
    finally:
        request_context.finish(token)

    line = project_log.getvalue().strip()
    assert line.endswith(f"WARNING request={reference} user=7 company=3 core.tests: Quota exceeded")
    assert line[:4].isdigit() and line[10] == "T" and "Z " in line  # ISO time in UTC


def test_log_lines_outside_a_request_show_dashes(project_log):
    logger.warning("Starting up")
    assert "request=- user=- company=-" in project_log.getvalue()


def test_context_is_cleared_after_the_request(project_log):
    token = request_context.start()
    request_context.bind_actor(user_id=7)
    request_context.finish(token)
    logger.warning("Later")
    assert "user=-" in project_log.getvalue()
