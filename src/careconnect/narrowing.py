"""Narrow an approved passage to the sentences that answer the request."""

import re

MAX_SENTENCES = 3
STOPWORDS = {
    "a", "an", "and", "are", "at", "can", "do", "for", "how", "i", "in", "is", "it", "me", "my",
    "of", "on", "the", "to", "what", "when", "where", "which", "who", "why", "you", "your",
}
SUFFIXES = ("ing", "ers", "ors", "er", "or", "es", "ed", "s", "e")


def _stem(word):
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _stems(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())} - STOPWORDS


def _sentences(text):
    """(heading, sentence) pairs in document order; each sentence is verbatim from the text."""
    heading = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        elif line:
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line):
                yield heading, sentence


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
    return [sentence for *_, index, sentence in sorted(best, key=lambda s: s[2])]
