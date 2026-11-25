"""The platform's Terms and Privacy text, the single copy the public pages show.

The owner supplies the wording after a legal review; none is written here. A document is a
title and sections of paragraphs. While a document has no sections its page says it is being
prepared. Any change to this text makes the saved legal review void (see legal_review.py).

    TERMS = {"title": "Terms", "sections": [{"heading": "...", "paragraphs": ["..."]}]}
"""

import hashlib
import json

TERMS = {"title": "Terms", "sections": []}
PRIVACY = {"title": "Privacy", "sections": []}

VERSION_LENGTH = 16


def documents():
    return {"terms": TERMS, "privacy": PRIVACY}


def is_written():
    """True when both documents have text, so there is something to review."""
    return all(document["sections"] for document in documents().values())


def current_version():
    """A short marker of the exact text: any change to either document changes it."""
    fingerprint = json.dumps(documents(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:VERSION_LENGTH]
