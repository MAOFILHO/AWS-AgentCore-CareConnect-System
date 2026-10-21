"""Supervisor seam: request in, outcome out."""

import uuid

from careconnect.budget import BUDGET_MESSAGE, BudgetExceeded, BudgetTracker, load_budgets
from careconnect.safety_gate import classify, is_health_request, mask_pii, sanitize_retrieved
from careconnect.verification import verify

NO_ANSWER = "I could not find an approved answer to that."
ESCALATION_NOTICE = "A licensed clinician will follow up with you."
ESCALATION_FAILED_NOTICE = (
    "We could not pass your request to a clinician. Please contact Riverside Health "
    "directly, or call emergency services if your symptoms are urgent."
)
CLINICAL_REASON = "Medication/clinical decision requires clinician review."
UNVERIFIED_REASON = "Answer could not be verified."


def supervisor_flow(
    request, knowledge_base, ticket_store, grounding, guardrail, document_processor=None,
    *, workflow, approved, cost_meter, budgets=None, clock=None,
):
    tracker = BudgetTracker(budgets or load_budgets(), cost_meter, clock)
    request_id = str(uuid.uuid4())
    try:
        return _flow(
            request, knowledge_base, ticket_store, workflow, grounding, guardrail, document_processor,
            approved, tracker, request_id,
        )
    except BudgetExceeded:
        return {
            "request_id": request_id, "citations": [], "escalation": None,
            "decision": "stop", "reply": BUDGET_MESSAGE,
        }


def _flow(
    request, knowledge_base, ticket_store, workflow, grounding, guardrail, document_processor,
    approved, tracker, request_id,
):
    gate = classify(request)
    outcome = {"request_id": request_id, "citations": [], "escalation": None}

    def escalate(reason, category):
        ticket = ticket_store.create({
            "request_id": outcome["request_id"], "text": mask_pii(request),
            "reason": reason, "category": category,
        })
        reply = ESCALATION_NOTICE
        try:
            workflow.start(ticket)
        except Exception:  # the ticket stays; promise nothing
            reply = ESCALATION_FAILED_NOTICE
        return {**outcome, "decision": "escalate", "reply": reply, "escalation": ticket}

    if gate["clinical"] or gate["urgent"] or is_health_request(request):
        return escalate(CLINICAL_REASON, "clinical_question")
    if gate["injection"]:
        return {**outcome, "decision": "block", "reply": "I can't help with that request."}
    tracker.step("retrieve")
    hits = [(name, sanitize_retrieved(text)) for name, text in knowledge_base.retrieve(request)]
    hits = [(name, text) for name, text in hits if text and name in (approved or ())]
    if not hits:
        return {**outcome, "decision": "allow", "reply": NO_ANSWER}
    draft = "\n".join(passage for _, passage in hits)
    if document_processor:
        tracker.step("document_processing")
        draft = document_processor.process(draft).text
    citations = [name for name, _ in hits]
    tracker.step("verify")
    result = verify(
        draft, citations, dict(hits), grounding, guardrail
    )
    if result.status != "PASS":
        return escalate(UNVERIFIED_REASON, "unverified_answer")
    return {**outcome, "decision": "allow", "reply": draft, "citations": citations}
