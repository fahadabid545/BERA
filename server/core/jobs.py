import functools
import logging
import traceback

from . import request_context
from .errors import AppError

logger = logging.getLogger(__name__)


def logged_job(function):
    """Wrap a background job so a failure is traceable but never reveals its data.

    The log gets the job name, the kind of error, where it happened and a
    reference. The error message and the arguments are left out, because they
    can contain CV text. The raised error carries only the reference, which is
    what the job queue stores.
    """

    @functools.wraps(function)
    def run(*args, **kwargs):
        token = request_context.start()
        try:
            return function(*args, **kwargs)
        except Exception as error:
            reference = request_context.current_reference()
            logger.error(
                "Background job %s failed with %s\n%s",
                function.__qualname__,
                type(error).__name__,
                "".join(traceback.format_tb(error.__traceback__)),
            )
            raise AppError(
                "job_failed",
                f"The background job failed. Reference: {reference}.",
                status_code=500,
                reference=reference,
            ) from None
        finally:
            request_context.finish(token)

    return run
