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


def _split_section(section):
    """(heading, body) of one "#"-led section; a flattened heading ends where its first sentence starts."""
    section = section.strip()
    if not section.startswith("#"):
        return "", section
    section = section.lstrip("#").strip()
    first_line, newline, rest = section.partition("\n")
    if newline:
        return first_line.strip(), rest
    words = list(re.finditer(r"\S+", section))
    for i in range(1, len(words) - 1):
        word = words[i].group()
        follows_question = words[i - 1].group().endswith("?")
        starts_sentence = follows_question or re.match(r"[a-z0-9]", words[i + 1].group())
        if word[0].isupper() and not word.endswith(",") and starts_sentence:
            first = re.match(r"[^.!?]*[.!](?=\s|$)", section[words[i].start():])
            if first and len(first.group().split()) >= 4:
                return section[: words[i].start()].strip(), section[words[i].start():]
    return section, ""


def _sentences(text):
    """(heading, sentence) pairs in document order; each sentence is verbatim from the text."""
    for section in re.split(r"(?<!\S)(?=#{1,6} )", text):
        heading, body = _split_section(section)
        for line in body.splitlines():
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line.strip()):
                if sentence:
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
    return [s for *_, s in sorted(best, key=lambda s: s[2])]
