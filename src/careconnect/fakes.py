"""In-memory fakes for the Knowledge Base and the escalation ticket store."""


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
