import io
import logging

import pytest

from core.logging_setup import RedactingFormatter, RequestContextFilter
from platform_settings import service as platform_settings_service


@pytest.fixture
def project_log():
    """Captures log output exactly as the project formats it."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(RedactingFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    yield stream
    root.removeHandler(handler)


@pytest.fixture(autouse=True)
def fresh_platform_settings():
    """Settings are cached for a short time; a value one test stored must not reach the next."""
    platform_settings_service.clear_cache()
    yield
    platform_settings_service.clear_cache()
