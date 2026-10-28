import pytest

from core.errors import AppError
from core.jobs import logged_job

CV_TEXT = "Jane Doe, 12 Example Street, worked at Acme Ltd as a welder"


@logged_job
def parse_cv(cv_text):
    raise ValueError(f"cannot read: {cv_text}")


@logged_job
def add(first, second):
    return first + second


def test_failing_job_logs_enough_to_understand_it_without_cv_text(project_log):
    with pytest.raises(AppError) as caught:
        parse_cv(CV_TEXT)

    reference = caught.value.reference
    log = project_log.getvalue()
    assert f"request={reference}" in log
    assert "parse_cv" in log and "ValueError" in log
    assert "test_jobs.py" in log  # where it happened
    assert "Jane Doe" not in log and "Acme" not in log


def test_failing_job_raises_an_error_that_carries_no_cv_text():
    with pytest.raises(AppError) as caught:
        parse_cv(CV_TEXT)

    error = caught.value
    assert error.code == "job_failed"
    assert error.reference in error.message
    assert "Jane Doe" not in str(error) and error.__cause__ is None
    assert error.__suppress_context__ is True


def test_successful_job_returns_its_result_and_logs_nothing(project_log):
    assert add(2, 3) == 5
    assert project_log.getvalue() == ""
