"""Supervisor seam: request in, outcome out."""

import uuid

from careconnect.safety_gate import classify, mask_pii, sanitize_retrieved

NO_ANSWER = "I could not find an approved answer to that."


def supervisor_flow(request, knowledge_base, ticket_store):
    gate = classify(request)
    outcome = {"request_id": str(uuid.uuid4()), "citations": [], "escalation": None}
    if gate["clinical"] or gate["urgent"]:
        ticket = ticket_store.create(
            {"request_id": outcome["request_id"], "text": mask_pii(request)}
        )
        reply = "A licensed clinician will follow up with you."
        return {**outcome, "decision": "escalate", "reply": reply, "escalation": ticket}
    if gate["injection"]:
        return {**outcome, "decision": "block", "reply": "I can't help with that request."}
    hits = [(name, sanitize_retrieved(text)) for name, text in knowledge_base.retrieve(request)]
    hits = [(name, text) for name, text in hits if text]
    if not hits:
        return {**outcome, "decision": "allow", "reply": NO_ANSWER}
    return {
        **outcome,
        "decision": "allow",
        "reply": "\n".join(passage for _, passage in hits),
        "citations": [name for name, _ in hits],
    }
