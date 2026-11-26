"""Picks the parts of the public documents that bear on one visitor question.

Sending every document with every question would cost far more than it helps, so the documents
are cut into chunks and only the chunks that share words with the question are sent, up to a
character budget (platform settings `chatbot.chunk_characters` and `chatbot.context_characters`).
With no match at all, the opening chunks of each document are sent instead, so a general question
such as "what is this product?" still has something to answer from.

Reads only `documents.knowledge_texts()`: public product information, never a company's data.
"""

import re

from platform_settings.service import get_setting

from . import documents

WORD = re.compile(r"[a-z0-9]{3,}")


def _words(text):
    return set(WORD.findall(text.lower()))


def _chunks(text, size):
    """The text in pieces of at most `size` characters, split at blank lines where possible."""
    pieces, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        while len(paragraph) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(paragraph[:size])
            paragraph = paragraph[size:].strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > size:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        pieces.append(current)
    return pieces


def excerpts_for(question):
    """[{"source", "excerpt"}] for the question, in document order, within the budget."""
    size = get_setting("chatbot.chunk_characters")
    budget = get_setting("chatbot.context_characters")
    wanted = _words(question)
    candidates = []  # (document position, chunk position, score, source, chunk)
    for position, (name, text) in enumerate(documents.knowledge_texts()):
        for index, chunk in enumerate(_chunks(text, size)):
            candidates.append((position, index, len(wanted & _words(chunk)), name, chunk))
    matching = [found for found in candidates if found[2] > 0]
    # Best matches first; with none, the opening chunks of each document in turn.
    ranked = (
        sorted(matching, key=lambda found: (-found[2], found[0], found[1]))
        if matching
        else sorted(candidates, key=lambda found: (found[1], found[0]))
    )
    chosen, used = [], 0
    for found in ranked:
        if used + len(found[4]) > budget:
            continue
        chosen.append(found)
        used += len(found[4])
    chosen.sort(key=lambda found: (found[0], found[1]))
    return [{"source": found[3], "excerpt": found[4]} for found in chosen]
