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


def _sections(text):
    """(heading, sentences) per section in document order; each sentence is verbatim from the text.

    A "#" run starts a new section and, when the text has line breaks, the section's first line
    is its heading. A flattened passage has no line breaks, so a heading runs into the first
    sentence: no heading is guessed, the section's first sentence stands in for it, and each
    section is split into sentences as it stands.
    """
    flat = "\n" not in text.strip()
    for section in re.split(r"(?<!\S)(?=#{1,6} )", text):
        heading, body = ("", section) if flat else _heading_and_body(section)
        sentences = []
        for line in body.splitlines():
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line.strip()):
                if sentence:
                    sentences.extend(_chunks(sentence) if flat else [sentence])
        if sentences:
            yield (sentences[0] if flat and sentences[0].startswith("#") else heading), sentences


def _sentences(text):
    for heading, sentences in _sections(text):
        for sentence in sentences:
            yield heading, sentence


def _heading_and_body(section):
    section = section.strip()
    if not section.startswith("#"):
        return "", section
    first_line, _, body = section.partition("\n")
    return first_line.strip(), body


def _score(weight, heading, sentences):
    """A document title ranks last, then request words in the heading and first sentence, then in the rest.

    A flat heading runs into its first sentence, so both kinds of passage are scored on the same lead.
    A word found in many sections counts for less than one found in a few.
    """
    lead = f"{heading} {sentences[0]}".strip()
    return (
        not lead.startswith("# "),
        sum(weight[w] for w in weight if w in _stems(lead)),
        sum(weight[w] for w in weight if w in _stems(" ".join(sentences[1:]))),
    )


def answer_sentences(request, text):
    """Up to MAX_SENTENCES verbatim sentences from the section that best answers the request.

    A section is scored by the request words in its heading and first sentence, then in the rest;
    a document title ranks last and a tie goes to the earlier section. In that section a sentence
    counts a request word from its own words or from the section heading, so "maternity" finds
    the sentences under "Maternity and birthing". Ties go to the earlier sentence. An empty list
    means nothing answers the request.
    """
    wanted = _stems(request)
    sections = list(_sections(text))
    found = [wanted & _stems(" ".join([heading, *sentences])) for heading, sentences in sections]
    weight = {w: 1 / sum(w in f for f in found) for w in wanted if any(w in f for f in found)}
    best = max(
        ((_score(weight, heading, sentences), -i, heading, sentences)
         for i, (heading, sentences) in enumerate(sections)),
        default=((False, 0, 0), 0, "", []),
    )
    if not any(best[0][1:]):
        return []
    _, _, heading, sentences = best
    in_heading = wanted & _stems(heading)
    scored = [
        (-len(in_heading | (wanted & _stems(sentence))), index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    scored = [row for row in scored if row[0]]
    return [s for *_, s in sorted(sorted(scored)[:MAX_SENTENCES], key=lambda s: s[1])]
