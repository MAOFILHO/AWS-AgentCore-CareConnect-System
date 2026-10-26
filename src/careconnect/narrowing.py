"""Narrow an approved passage to the sentences that answer the request."""

import re

MAX_SENTENCES = 3
MAX_CHARS = 400
STOPWORDS = {
    "a", "an", "and", "are", "at", "can", "do", "for", "how", "i", "in", "is", "it", "me", "my",
    "of", "on", "the", "to", "what", "when", "where", "which", "who", "why", "you", "your",
}
SUFFIXES = ("ing", "ers", "ors", "er", "or", "es", "ed", "s")


def _stem(word):
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stems(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())} - STOPWORDS


def _chunks(piece):
    """A flat piece in parts of at most MAX_CHARS, cut at spaces, so no text is dropped."""
    while len(piece) > MAX_CHARS and " " in piece[:MAX_CHARS]:
        head = piece[:MAX_CHARS].rsplit(" ", 1)[0]
        yield head
        piece = piece[len(head):].lstrip()
    yield piece


def _sentences(text):
    """(heading, sentence) pairs in document order; each sentence is verbatim from the text.

    A "#" run starts a new section and, when the text has line breaks, the section's first line
    is its heading. A flattened passage has no line breaks, so a heading runs into the first
    sentence: no heading is guessed and each section is split into sentences as it stands.
    """
    flat = "\n" not in text.strip()
    for section in re.split(r"(?<!\S)(?=#{1,6} )", text):
        heading, body = ("", section) if flat else _heading_and_body(section)
        for line in body.splitlines():
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line.strip()):
                if sentence:
                    for part in _chunks(sentence) if flat else [sentence]:
                        yield heading, part


def _heading_and_body(section):
    section = section.strip()
    if not section.startswith("#"):
        return "", section
    first_line, _, body = section.partition("\n")
    return first_line.lstrip("#").strip(), body


def answer_sentences(request, text):
    """Up to MAX_SENTENCES verbatim sentences that share a word with the request, in document order.

    A request word may match the sentence or its section heading, so "maternity" finds the
    sentences under "Maternity and birthing". Ties go to the heading match, then to the
    earlier sentence. An empty list means nothing answers the request.
    """
    wanted = _stems(request)
    scored = []
    for index, (heading, sentence) in enumerate(_sentences(text)):
        in_heading = wanted & _stems(heading)
        matched = len(in_heading | (wanted & _stems(sentence)))
        if matched:
            scored.append((-matched, -len(in_heading), index, sentence))
    best = sorted(scored)[:MAX_SENTENCES]
    return [s for *_, s in sorted(best, key=lambda s: s[2])]
