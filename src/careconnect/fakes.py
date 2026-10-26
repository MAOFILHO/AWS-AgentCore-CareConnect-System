"""In-memory fakes for the Knowledge Base, the escalation ticket store, the Gateway MCP client and the Task/Tool Agent."""

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


class FakeApprovalWorkflow:
    def __init__(self, error=False):
        self.error = error
        self.started = []

    def start(self, ticket):
        if self.error:
            raise RuntimeError("workflow unavailable")
        self.started.append(ticket)
        return "fake-execution"


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


class FakeMcpClient:
    """Stands in for the Gateway MCP client: a context manager that lists no tools."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def list_tools_sync(self):
        return []


class FakeTaskAgent:
    """Stands in for the Task/Tool Agent: replies "done" and keeps the given tool messages."""

    def __init__(self, messages):
        self.messages = messages

    def __call__(self, request):
        return "done"
