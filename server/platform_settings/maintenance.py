"""Maintenance mode: while it is on, companies are told why and cannot upload; everything else,
admin sign-in included, works as usual."""

from core.errors import AppError

from .service import get_setting

CODE = "maintenance_mode"


def is_on():
    return get_setting("maintenance.enabled")


def message():
    return get_setting("maintenance.message")


def refusal():
    return AppError(CODE, message(), status_code=503)


def refuse_if_on():
    if is_on():
        raise refusal()
