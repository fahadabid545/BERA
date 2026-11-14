"""The steps that exist so far, plugged into their slots (see `processing.py`)."""

import privatefiles
from privatefiles import StoredFileMissing

from .duplicates import review_likely_duplicate
from .processing import PermanentFailure, StepContext, register_step
from .text_reading import CvTextUnreadable, read_text

FILE_MISSING = "This file could not be found. Please upload it again."


def read_the_text(context: StepContext):
    """Slot `text_reading`: the text of the CV, kept for the later steps of this try, and a look
    for a CV of the same person. A file with no readable text fails for good (not counted)."""
    cv_file = context.cv_file
    try:
        data = privatefiles.read_file(cv_file.storage_key)
    except StoredFileMissing as error:
        raise PermanentFailure(FILE_MISSING) from error
    try:
        text = read_text(cv_file.file_type, data).text
    except CvTextUnreadable as error:
        raise PermanentFailure(error.message) from error
    context.state["text"] = text
    review_likely_duplicate(cv_file, text)


register_step("text_reading", read_the_text)
