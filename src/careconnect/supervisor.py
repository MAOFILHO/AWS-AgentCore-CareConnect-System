"""Supervisor seam: request in, outcome out."""

import logging
import re
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
TASK_REASON = "Task request could not be completed safely."

log = logging.getLogger(__name__)


def _log_outcome(request_id, decision, outcome):
    """One record per request: IDs and labels only, never the message text."""
    log.info("request_id=%s safety_gate=%s outcome=%s", request_id, decision, outcome)


def _outcome_label(out):
    if out["decision"] == "escalate":
        return "escalation_failed" if out["reply"] == ESCALATION_FAILED_NOTICE else "escalation"
    return {"allow": "answer", "block": "block", "stop": "stop"}[out["decision"]]


def supervisor_flow(
    request, knowledge_base, ticket_store, grounding, guardrail, document_processor=None,
    *, workflow, approved, cost_meter, budgets=None, clock=None, gateway=None, idempotency_key=None,
    patient_reference=None,
):
    tracker = BudgetTracker(budgets or load_budgets(), cost_meter, clock)
    request_id = str(uuid.uuid4())
    try:
        out = _flow(
            request, knowledge_base, ticket_store, workflow, grounding, guardrail, document_processor,
            approved, tracker, request_id, gateway, idempotency_key, patient_reference,
        )
    except BudgetExceeded:
        out = {
            "request_id": request_id, "citations": [], "escalation": None,
            "decision": "stop", "reply": BUDGET_MESSAGE,
        }
    except Exception:  # no message text or error text in logs
        _log_outcome(request_id, "unknown", "error")
        raise
    _log_outcome(request_id, out["decision"], _outcome_label(out))
    return {**out, "reply": mask_pii(out["reply"])}


def _flow(
    request, knowledge_base, ticket_store, workflow, grounding, guardrail, document_processor,
    approved, tracker, request_id, gateway=None, idempotency_key=None, patient_reference=None,
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
    if gateway:
        task = _task_reply(request, gateway, idempotency_key, patient_reference, tracker)
        if task == "escalate":
            return escalate(TASK_REASON, "task_request")
        if task:
            return {**outcome, "decision": "allow", **task}
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


REFILL_REQUEST = re.compile(r"\brefill\s+(?:of|for|my)\s+(?:my\s+)?(\w+)", re.IGNORECASE)


NOT_A_DRUG = {"me", "my", "us", "it", "them"}


def _task_reply(request, gateway, idempotency_key, patient_reference, tracker):
    """Task/Tool agent seam: staged reply, "escalate" on a rejected refill, None if not a task."""
    refill = REFILL_REQUEST.search(request)
    if refill:
        tracker.step("task_tool")
        if not patient_reference:  # fail closed: no authenticated patient, a human decides
            return "escalate"
        if refill.group(1).lower() in NOT_A_DRUG:  # fail closed: no drug named, a human decides
            return "escalate"
        try:
            staged = gateway.stage_refill_request(patient_reference, refill.group(1), idempotency_key)
        except ValueError:  # fail closed: a refill without a key is never staged
            return "escalate"
        return {
            "reply": f"Your {staged.drug} refill is staged and awaits human approval. "
            "It has not been submitted.",
            "task": staged.model_dump(exclude={"patient_reference"}),
        }
    if re.search(r"\bappointment status\b", request, re.IGNORECASE):
        tracker.step("task_tool")
        if not patient_reference:  # fail closed: no authenticated patient, a human decides
            return "escalate"
        status = gateway.check_appointment_status(patient_reference)
        return {
            "reply": f"Your {status.department} appointment {status.appointment_reference} "
            f"is {status.appointment_status}.",
            "task": status.model_dump(exclude={"patient_reference"}),
        }
    return None
