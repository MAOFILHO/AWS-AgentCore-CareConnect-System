"""
CareConnect — Supervisor Agent (Orchestrator)
=============================================
Riverside Health patient-support assistant (console/CLI build).

WHAT THIS AGENT DOES
  This is the "brain" that coordinates the four specialist agents you built:
    retrieval_agent.py     -> approved Knowledge Base lookups
    task_tool_agent.py     -> operational actions via AgentCore Gateway (MCP)
    escalation_agent.py    -> human-review tickets + Step Functions
    verification_agent.py  -> grounding + deterministic safety + guardrail
  For each patient request it: runs a safety check, plans which agents are
  needed, runs them, combines only the SAFE outputs into a draft, and verifies
  that draft before returning it. Clinical questions are escalated, never answered.
  It also enforces step/time budgets so it can't run away.

>>> IMPORTANT FOR LEARNERS <<<
  All FOUR agent files (retrieval_agent.py, task_tool_agent.py,
  escalation_agent.py, verification_agent.py) live in the same package as this
  file (careconnect.agents), and this script imports from them.

HOW TO USE
  1. Export all the environment variables first (KB ID, Gateway URL, Guardrail
     ID/version, State Machine ARN) — see the "environment variables" block in
     the guide. Each is marked ">>> LEARNERS" below where it's used.
  2. Run it:
         PYTHONPATH=src python3 -m careconnect.agents.supervisor_agent
  3. Type a patient request; type 'exit' to stop.
"""

import logging
import os
import re
import uuid

# Specialist agents live in the same package; run with PYTHONPATH=src.
from pydantic import ValidationError

from careconnect.agents.escalation_agent import escalate
from careconnect.agents.verification_agent import get_guardrail_settings, verify
from careconnect.api_reply import ApiReply
from careconnect.budget import (
    BUDGET_MESSAGE, BudgetExceeded, BudgetTracker, UnmeteredCost, load_budgets,
)
from careconnect.gateway import StagedRefillToolReply
from careconnect.safety_gate import classify, is_health_request, mask_pii, sanitize_retrieved
from careconnect.supervisor import ESCALATION_FAILED_NOTICE, ESCALATION_NOTICE, REFILL_REQUEST
from careconnect.supervisor_model import load_supervisor_model

BLOCK_NOTICE = "I can't help with that request."
STAGED_NOTICE = "Your refill is staged and awaits human approval. It has not been submitted."
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Safety gate: the shared rules in careconnect.safety_gate decide.
#    The Supervisor keeps no pattern list of its own.
# ---------------------------------------------------------------------------
def check_safety(request, state):
    state.step("Safety gate (input check)")
    gate = classify(request)
    escalate_request = bool(
        gate["clinical"] or gate["urgent"] or is_health_request(request)
    )
    return {
        "clinical_detected": escalate_request,
        "blocked": bool(gate["injection"]) and not escalate_request,
    }


# ---------------------------------------------------------------------------
# 2. Planning: split a multi-intent request into tasks, each tagged with an agent.
#    >>> LEARNERS: REPLACE these keyword lists for your own request types.
# ---------------------------------------------------------------------------
INFORMATIONAL_KEYWORDS = [
    "prepare", "preparation", "how do i", "colonoscopy", "visiting hours",
    "policy", "refill process", "timing", "refill", "park", "parking",
    "appointment", "book", "hours",
]
OPERATIONAL_KEYWORDS = ["reschedule", "cancel booking"]
REFILL_QUESTION_MARKERS = ["how do i", "how to", "policy", "process"]


def is_refill_action(lowered):
    return bool(REFILL_REQUEST.search(lowered)) and not any(m in lowered for m in REFILL_QUESTION_MARKERS)


def create_plan(request, safety, state):
    state.step("Create execution plan")
    lowered = request.lower()
    plan = []
    if safety["clinical_detected"]:  # fail closed: escalate only, no retrieval
        return [{"task": "Medication / clinical decision", "agent": "escalation"}]
    if is_refill_action(lowered):  # a real refill action: the task agent alone stages it
        plan.append({"task": "Stage refill request", "agent": "task"})
        print(f"     - {plan[0]['task']} -> task agent")
        return plan
    if any(k in lowered for k in INFORMATIONAL_KEYWORDS):
        plan.append({"task": "Retrieve approved information", "agent": "retrieval"})
    if any(k in lowered for k in OPERATIONAL_KEYWORDS):
        plan.append({"task": "Check operational status", "agent": "task"})
    if not plan:
        plan.append({"task": "General approved-information lookup", "agent": "retrieval"})
    for p in plan:
        print(f"     - {p['task']} -> {p['agent']} agent")
    return plan


# ---------------------------------------------------------------------------
# 3. Route + execute each task on its real specialist agent.
# ---------------------------------------------------------------------------
def run_retrieval(request, state):
    state.step("Retrieval Agent")
    # >>> LEARNERS: export CARECONNECT_KB_ID="<your-kb-id>"
    if not os.environ.get("CARECONNECT_KB_ID"):
        return {"answer": "[retrieval skipped: CARECONNECT_KB_ID not set]", "passages": ""}
    from careconnect.agents.retrieval_agent import search_docs
    all_passages = sanitize_retrieved(search_docs(request))
    # Keep only the single top-ranked passage. Semantic search returns several
    # loosely-related chunks; extra ones (e.g. triage/dosage text) can trip the
    # guardrail even for a simple question. Verifying against the best-matching
    # passage keeps the draft grounded AND clear of unrelated safety triggers.
    # Passages whose Source is not under approved/ are dropped before the draft.
    top = next((p.strip() for p in split_passages(all_passages) if approved_sources(p)), "")
    return {"answer": top, "passages": top}


def split_passages(text):
    """One chunk per passage, each ending at its Source URI line."""
    blocks = re.split(r"^Passage \d+\s*$", text, flags=re.MULTILINE)
    return [c for b in blocks for c in re.findall(r"(?s).*?^Source:[ \t]*\n\S+", b, flags=re.MULTILINE)]


def tool_short_name(name):
    """Gateway tool names are '<target>___<tool>'."""
    return name.split("___")[-1]


def refill_was_staged(messages):
    """True only if a stage_refill_request tool call returned awaiting_approval, not submitted."""
    staging_calls = {
        block["toolUse"]["toolUseId"]
        for m in messages for block in m.get("content", [])
        if isinstance(block, dict) and tool_short_name(block.get("toolUse", {}).get("name", "")) == "stage_refill_request"
    }
    for m in messages:
        for block in m.get("content", []):
            result = block.get("toolResult") if isinstance(block, dict) else None
            if not result or result.get("toolUseId") not in staging_calls or result.get("status") == "error":
                continue
            for part in result.get("content", []):
                try:
                    if "json" in part:
                        StagedRefillToolReply.model_validate(part["json"], strict=True)
                    else:
                        StagedRefillToolReply.model_validate_json(part["text"], strict=True)
                except (ValidationError, KeyError, TypeError):
                    continue
                return True
    return False


def run_task_tool(request, state):
    """Returns {"reply": text, "staged": True only when the Gateway staged a refill}."""
    state.step("Task/Tool Agent (AgentCore Gateway / MCP)")
    # >>> LEARNERS: export CARECONNECT_GATEWAY_URL="<your-gateway-mcp-url>"
    if not os.environ.get("CARECONNECT_GATEWAY_URL"):
        return {"reply": "[task/tool skipped: CARECONNECT_GATEWAY_URL not set]", "staged": False}
    model = load_supervisor_model()  # a config error must not read as a gateway error
    try:
        from careconnect.agents.task_tool_agent import SYSTEM_PROMPT, get_mcp_client
        from strands import Agent
        with get_mcp_client() as mcp_client:
            tools = mcp_client.list_tools_sync()
            agent = Agent(system_prompt=SYSTEM_PROMPT, tools=tools, model=model)
            reply = str(agent(request))
            return {"reply": reply, "staged": refill_was_staged(agent.messages)}
    except Exception:
        return {"reply": "[task/tool agent error - gateway call failed]", "staged": False}


def run_escalation(request, state):
    state.step("Escalation Agent")
    # >>> LEARNERS: export CARECONNECT_STATE_MACHINE_ARN="<your-arn>"
    # Real side effects: writes a DynamoDB ticket + starts Step Functions.
    return escalate(
        reason="Medication/clinical decision requires clinician review.",
        category="clinical_question",
        request_details={"patient_request": mask_pii(request)},
    )


def execute_required_agents(request, plan, state):
    results = {}
    for item in plan:
        agent = item["agent"]
        if agent == "retrieval" and "retrieval" not in results:
            results["retrieval"] = run_retrieval(request, state)
        elif agent == "task" and "task" not in results:
            results["task"] = run_task_tool(request, state)
        elif agent == "escalation" and "escalation" not in results:
            results["escalation"] = run_escalation(request, state)
    return results


# ---------------------------------------------------------------------------
# 4. Combine only the SAFE outputs into a patient-facing draft.
#    Returns BOTH the draft and the evidence (raw passages) it was built from.
# ---------------------------------------------------------------------------
def combine_safe_results(results, safety, state):
    state.step("Combine safe results")
    parts = []
    evidence = ""
    if "retrieval" in results:
        evidence = results["retrieval"].get("passages", "")
        parts.append("Approved Riverside Health information:\n" + evidence)
    if "task" in results:
        parts.append("Operational status:\n" + results["task"]["reply"])
    if "escalation" in results:
        esc = results["escalation"]
        # Never surface a clinical answer - only the escalation notice.
        parts.append(
            "Medication question:\n"
            "Your medication question requires review by a licensed "
            f"clinician. (Ticket: {esc.get('ticket_id', 'n/a')}, "
            f"status: {esc.get('status', 'pending_review')})"
        )
    elif safety["clinical_detected"]:
        parts.append(ESCALATION_NOTICE)
    return "\n\n".join(parts), evidence


# ---------------------------------------------------------------------------
# 5. Verify the draft against the SAME passages retrieval returned.
#    Syncs retrieved_passages.txt so the verifier checks live evidence.
# ---------------------------------------------------------------------------
def verify_response(draft, evidence, state):
    state.step("Verification Agent")
    if not evidence.strip():
        return {"verification_status": "SKIPPED", "reason": "no evidence available"}
    with open("retrieved_passages.txt", "w", encoding="utf-8") as f:
        f.write(evidence)
    try:
        return verify(draft, evidence)
    except Exception as exc:
        return {"verification_status": "ERROR", "reason": str(exc)}


def escalation_notice(request):
    """Open the clinician ticket first; promise a follow-up only if it exists."""
    try:
        escalate(
            reason="Answer could not be verified.",
            category="unverified_answer",
            request_details={"patient_request": mask_pii(request)},
        )
    except Exception:
        return ESCALATION_FAILED_NOTICE
    return ESCALATION_NOTICE


# ---------------------------------------------------------------------------
# Orchestrator — ties the five stages together.
# ---------------------------------------------------------------------------
def supervisor_flow(request, *, cost_meter=None, budgets=None, clock=None):
    out = _supervisor_flow(request, cost_meter=cost_meter, budgets=budgets, clock=clock)
    return {**out, "draft_response": mask_pii(out["draft_response"])}


def _supervisor_flow(request, *, cost_meter=None, budgets=None, clock=None):
    state = BudgetTracker(budgets or load_budgets(), cost_meter or UnmeteredCost(), clock)
    request_id = str(uuid.uuid4())
    outcome = {"request_id": request_id, "request": mask_pii(request), "plan": [], "verification": {"verification_status": "n/a"}}
    try:
        safety = check_safety(request, state)
        outcome["safety"] = safety
        if safety["blocked"]:
            return {**outcome, "decision": "block", "draft_response": BLOCK_NOTICE}
        plan = create_plan(request, safety, state)
        outcome["plan"] = plan
        results = execute_required_agents(request, plan, state)
        draft, evidence = combine_safe_results(results, safety, state)
        if safety["clinical_detected"]:
            return {**outcome, "decision": "escalate", "draft_response": draft}
        if results.get("task", {}).get("staged"):  # fixed reply: never the model's free text
            return {**outcome, "decision": "allow", "draft_response": STAGED_NOTICE, "staged": True}
        verification = verify_response(draft, evidence, state)
    except BudgetExceeded:
        return {**outcome, "decision": "stop", "draft_response": BUDGET_MESSAGE}
    except Exception:  # fail closed: never show the draft; no message text or error text in logs
        clinical = bool(outcome.get("safety", {}).get("clinical_detected"))
        result = "escalation_failed" if clinical else "flow_failed"
        log.error("request_id=%s safety_gate=%s outcome=%s", request_id,
                  "escalate" if clinical else "allow", result)
        notice = ESCALATION_FAILED_NOTICE if clinical else escalation_notice(request)
        return {**outcome, "decision": "escalate", "draft_response": notice}
    citations = approved_sources(evidence)
    if verification.get("verification_status") != "PASS" or (evidence.strip() and not citations):
        return {**outcome, "decision": "escalate", "draft_response": escalation_notice(request),
                "verification": verification}  # withhold the draft
    return {**outcome, "decision": "allow", "draft_response": draft, "verification": verification,
            "citations": citations}


def approved_sources(evidence):
    """Citations are the retrieval Source URIs under approved/ only."""
    uris = re.findall(r"^Source:\s*\n(s3://[^\s/]+/approved/\S+)", evidence, flags=re.MULTILINE)
    return sorted(set(uris))


def api_result(outcome):
    """The API reply: decision, reply, citations and staged only. Never the request text."""
    return ApiReply(
        decision=outcome["decision"],
        reply=outcome["draft_response"],
        citations=outcome.get("citations", []),
        staged=outcome.get("staged", False),
    ).model_dump()


# ---------------------------------------------------------------------------
# Interactive terminal loop.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    get_guardrail_settings()  # fail closed: refuse to start without a Guardrail
    load_supervisor_model()  # and without a valid model config
    print("\nCareConnect Supervisor Agent")
    print("Type 'exit' to stop.\n")

    while True:
        request = input("Patient request: ").strip()

        if request.lower() in ["exit", "quit"]:
            print("Supervisor Agent stopped.")
            break

        if not request:
            continue

        outcome = supervisor_flow(request)

        print("\n--- Draft response ---\n")
        print(outcome["draft_response"])
        print("\n--- Verification ---")
        print(outcome.get("verification", {}).get("verification_status", "n/a"))
        print()
