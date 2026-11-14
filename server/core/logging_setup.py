"""Log format and the safety net that keeps secrets and personal data out of logs.

The main protection is never to log request bodies, headers or CV text. The
formatter then scrubs anything that still looks sensitive, as a second layer.
"""

import logging
import re
import time

from . import request_context

REDACTED = "[REDACTED]"
NOT_KNOWN = "-"

_SENSITIVE_NAME = (
    r"[\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|cv_text|resume_text"
    r"|phone|address|contact|full_name|date_of_birth|candidate_name)"
    r"[\w-]*"
)
_VALUE = r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^\s,&}\]]+"
_PATTERNS = [
    # First, so a number written with spaces is taken whole before the rule below sees it.
    # A phone number written with a plus or with a bracketed area code. Plain digit groups
    # (dates, ids, versions) are left alone so log lines stay readable.
    (re.compile(r"(?<![\w.])(?:\+\d[\d\s().-]{6,}\d|\(\d{2,5}\)[\d\s.-]{4,}\d)"), REDACTED),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), rf"\1 {REDACTED}"),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), REDACTED),
    (
        re.compile(rf"(?i)([\"']?{_SENSITIVE_NAME}[\"']?\s*[:=]\s*)(?!\[REDACTED\])({_VALUE})"),
        rf"\1{REDACTED}",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
]


def redact(text):
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        context = request_context.current()
        record.request_id = context.get("request_id") or NOT_KNOWN
        record.user_id = context.get("user_id") or NOT_KNOWN
        record.company_id = context.get("company_id") or NOT_KNOWN
        return True


class RedactingFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self):
        super().__init__(
            fmt=(
                "%(asctime)s %(levelname)s request=%(request_id)s user=%(user_id)s "
                "company=%(company_id)s %(name)s: %(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )

    def format(self, record):
        return redact(super().format(record))
