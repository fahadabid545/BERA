import io
import logging
from pathlib import Path

import pytest

from core.logging_setup import RedactingFormatter, RequestContextFilter
from core.tests.security_suite import SECURITY_TEST_FILES
from platform_settings import service as platform_settings_service

SERVER_ROOT = Path(__file__).parent


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


def pytest_collection_modifyitems(items):
    """The security suite is the test files named in core/tests/security_suite.py."""
    for item in items:
        path = Path(item.fspath)
        # Tests outside the server folder (the scripts tests) are not part of the suite.
        if path.is_relative_to(SERVER_ROOT) and (
            path.relative_to(SERVER_ROOT).as_posix() in SECURITY_TEST_FILES
        ):
            item.add_marker(pytest.mark.security)


@pytest.fixture(autouse=True)
def private_files_folder(settings, tmp_path):
    """Uploaded files in tests go to a throw-away folder, never into the project."""
    settings.PRIVATE_FILES_ROOT = tmp_path / "private-files"
