"""In-memory fakes for the Knowledge Base and the escalation ticket store."""

import re


class FakeKnowledgeBase:
    def __init__(self, documents):
        self.documents = documents  # {document name: text}

    def retrieve(self, query):
        """Return (document name, passage) pairs whose text shares a word with the query."""
        words = set(query.lower().split())
        return [
            (name, text)
            for name, text in self.documents.items()
            if words & set((name + " " + text).lower().replace("-", " ").split())
        ]


class FakeEscalationTicketStore:
    def __init__(self):
        self.tickets = []

    def create(self, ticket):
        self.tickets.append(ticket)
        return ticket


class FakeGrounding:
    """Grounding check: the draft must be supported by the cited passages."""

    def __init__(self, grounded=True, error=False):
        self.grounded = grounded
        self.error = error

    def check(self, draft, passages):
        if self.error:
            raise RuntimeError("grounding unavailable")
        text = "\n".join(passages)
        return self.grounded and all(
            re.sub(r"^\d+\. ", "", line) in text for line in draft.splitlines()
        )


class FakeGuardrail:
    def __init__(self, allow=True, error=False):
        self.allow = allow
        self.error = error

    def check(self, draft):
        if self.error:
            raise RuntimeError("guardrail unavailable")
        return self.allow


class FakeCostMeter:
    def __init__(self, cost_per_step=0.0):
        self.cost_per_step = cost_per_step
        self.total = 0.0

    def charge(self, name):
        self.total += self.cost_per_step
