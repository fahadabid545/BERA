"""Who and what the current work belongs to, so every log line can say so.

One context exists per web request or background job. Only identifiers are
kept here (never names or emails).
"""

import secrets
from contextvars import ContextVar

_context = ContextVar("request_context", default=None)


def new_reference():
    """A short code a user can read out and a developer can search the log for."""
    return secrets.token_hex(4).upper()


def start():
    return _context.set({"request_id": new_reference(), "user_id": None, "company_id": None})


def finish(token):
    _context.reset(token)


def bind_actor(user_id=None, company_id=None):
    """Called by sign-in code once it knows who is acting."""
    context = _context.get()
    if context is not None:
        if user_id is not None:
            context["user_id"] = user_id
        if company_id is not None:
            context["company_id"] = company_id


def current():
    return _context.get() or {}


def current_reference():
    return current().get("request_id")
