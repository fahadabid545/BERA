import io
import logging

import pytest

from core.logging_setup import RedactingFormatter, RequestContextFilter


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
