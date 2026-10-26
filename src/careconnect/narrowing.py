"""Narrow an approved passage to the sentences that answer the request."""

import re

MAX_SENTENCES = 3
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


def _is_flat(text):
    return "\n" not in text.strip() and re.search(r"#{1,6} ", text)


def _flat_sentences(text):
    """(section, sentence) pairs of a passage with no line breaks, split only on its "#" markers.

    No heading is guessed: a heading runs into its first sentence, so the whole section is the
    context. The title section (from "# " to the first "## ") and a sentence that is only a heading
    question are left out, and the leading "#" run of a quoted sentence is stripped.
    """
    for section in re.split(r"(?<!\S)(?=#{1,6} )", text):
        if re.match(r"# ", section):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", section.strip()):
            if sentence and not (sentence.startswith("#") and sentence.endswith("?")):
                yield section, re.sub(r"^#{1,6} ", "", sentence)


def answer_sentences(request, text):
    """Up to MAX_SENTENCES verbatim sentences that share a word with the request, in document order.

    A request word may match the sentence or its section heading, so "maternity" finds the
    sentences under "Maternity and birthing". Ties go to the heading match, then to the
    earlier sentence. A passage with no line breaks has no heading line, so a word of the
    sentence counts three times and a word of the rest of its section counts once. An empty list
    means nothing answers the request.
    """
    wanted = _stems(request)
    flat = _is_flat(text)
    scored = []
    for index, (heading, sentence) in enumerate(_flat_sentences(text) if flat else _sentences(text)):
        in_heading = wanted & _stems(heading)
        own = wanted & _stems(sentence)
        matched = 2 * len(own) + len(in_heading) if flat else len(in_heading | own)
        if matched:
            scored.append((-matched, 0 if flat else -len(in_heading), index, sentence))
    best = sorted(scored)[:MAX_SENTENCES]
    return [s for *_, s in sorted(best, key=lambda s: s[2])]
