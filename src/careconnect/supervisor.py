"""Supervisor seam: request in, outcome out."""

import uuid

from careconnect.fakes import FakeGrounding, FakeGuardrail
from careconnect.safety_gate import classify, is_health_request, mask_pii, sanitize_retrieved
from careconnect.verification import verify

NO_ANSWER = "I could not find an approved answer to that."
ESCALATION_NOTICE = "A licensed clinician will follow up with you."


def supervisor_flow(
    request, knowledge_base, ticket_store, grounding=None, guardrail=None
):
    gate = classify(request)
    outcome = {"request_id": str(uuid.uuid4()), "citations": [], "escalation": None}

    def escalate():
        ticket = ticket_store.create(
            {"request_id": outcome["request_id"], "text": mask_pii(request)}
        )
        return {
            **outcome,
            "decision": "escalate",
            "reply": ESCALATION_NOTICE,
            "escalation": ticket,
        }

    if gate["clinical"] or gate["urgent"] or is_health_request(request):
        return escalate()
    if gate["injection"]:
        return {**outcome, "decision": "block", "reply": "I can't help with that request."}
    hits = [(name, sanitize_retrieved(text)) for name, text in knowledge_base.retrieve(request)]
    hits = [(name, text) for name, text in hits if text]
    if not hits:
        return {**outcome, "decision": "allow", "reply": NO_ANSWER}
    draft = "\n".join(passage for _, passage in hits)
    citations = [name for name, _ in hits]
    result = verify(
        draft, citations, dict(hits), grounding or FakeGrounding(), guardrail or FakeGuardrail()
    )
    if result.status != "PASS":
        return escalate()
    return {**outcome, "decision": "allow", "reply": draft, "citations": citations}
