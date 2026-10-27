"""
CareConnect — Supervisor Agent (Orchestrator)
=============================================
Riverside Health patient-support assistant (console/CLI build).

WHAT THIS AGENT DOES
  This is the "brain" that coordinates the four specialist agents you built:
    retrieval_agent.py     -> approved Knowledge Base lookups
    task_tool_agent.py     -> operational actions via AgentCore Gateway (MCP)
    escalation_agent.py    -> human-review tickets + Step Functions
    verification_agent.py  -> grounding + relevance + deterministic safety + guardrail
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
from careconnect.agents.verification_agent import approved_phones, get_guardrail_settings, verify
from careconnect.api_reply import ApiReply
from careconnect.budget import (
    BUDGET_MESSAGE, BudgetExceeded, BudgetTracker, StepPriceMeter, load_budgets,
)
from careconnect.gateway import StagedRefillToolReply
from careconnect.narrowing import answer_sentences
from careconnect.safety_gate import classify, is_health_request, mask_pii, sanitize_retrieved
from careconnect.supervisor import ESCALATION_FAILED_NOTICE, ESCALATION_NOTICE, REFILL_REQUEST
from careconnect.supervisor_model import load_supervisor_model

BLOCK_NOTICE = "I can't help with that request."
STAGED_NOTICE = "Your refill is staged and awaits human approval. It has not been submitted."
OTHER_REQUEST_NOTICE = "Please ask separately about your other request."
UNANSWERED_NOTICE = "I ran out of time to answer your other question; please ask it again."
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
QUESTION_WORDS = ("how", "what", "when", "where", "why", "which", "who")


def is_refill_request(request):
    """An explicit 'refill my X' request, not a question about the refill process."""
    return bool(REFILL_REQUEST.search(request)) and not request.lower().lstrip().startswith(QUESTION_WORDS)


def create_plan(request, safety, state):
    state.step("Create execution plan")
    lowered = request.lower()
    plan = []
    if safety["clinical_detected"]:  # fail closed: escalate only, no retrieval
        return [{"task": "Medication / clinical decision", "agent": "escalation"}]
    if any(k in lowered for k in INFORMATIONAL_KEYWORDS):
        plan.append({"task": "Retrieve approved information", "agent": "retrieval"})
    if any(k in lowered for k in OPERATIONAL_KEYWORDS) or is_refill_request(request):
        plan.append({"task": "Check operational status", "agent": "task"})
    if not plan:
        plan.append({"task": "General approved-information lookup", "agent": "retrieval"})
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
    blocks = [b for m in messages if isinstance(m, dict) for b in m.get("content", []) if isinstance(b, dict)]
    staging_calls = {
        use["toolUseId"] for use in (b.get("toolUse") for b in blocks)
        if isinstance(use, dict) and use.get("toolUseId")
        and tool_short_name(use.get("name", "")) == "stage_refill_request"
    }
    for block in blocks:
        result = block.get("toolResult")
        if not isinstance(result, dict) or result.get("toolUseId") not in staging_calls or result.get("status") == "error":
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
def narrowed_passage(request, evidence):
    """The sentences of the passage that answer the request, then its Source line. "" if none do."""
    match = re.search(r"(?s)\A(.*?)^Source:[ \t]*\n(\S+)", evidence, flags=re.MULTILINE)
    sentences = answer_sentences(request, match.group(1)) if match else []
    return "\n".join(sentences + ["Source:", match.group(2)]) if sentences else ""


def combine_safe_results(request, results, safety, state):
    state.step("Combine safe results")
    parts = []
    evidence = ""
    if "retrieval" in results:
        evidence = results["retrieval"].get("passages", "")
        answer = narrowed_passage(request, evidence)
        if answer:
            parts.append("Approved Riverside Health information:\n" + answer)
        else:  # nothing answers the request: no evidence, so the flow escalates
            evidence = ""
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
# ---------------------------------------------------------------------------
def verify_response(request, draft, evidence, state):
    state.step("Verification Agent")
    if not evidence.strip():
        return {"verification_status": "SKIPPED", "reason": "no evidence available"}
    try:
        return verify(request, draft, evidence)
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
    keep = out.pop("approved_phones", ())
    return {**out, "draft_response": mask_pii_except(out["draft_response"], keep)}


def mask_pii_except(text, keep):
    """mask_pii, but the phone numbers in keep stay as written."""
    keep = sorted(keep)
    for index, number in enumerate(keep):
        text = text.replace(number, f"\0{index}\0")
    return re.sub(r"\0(\d+)\0", lambda m: keep[int(m.group(1))], mask_pii(text))


def _supervisor_flow(request, *, cost_meter=None, budgets=None, clock=None):
    budgets = budgets or load_budgets()
    state = BudgetTracker(budgets, cost_meter or StepPriceMeter(budgets.step_cost_usd), clock)
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
        draft, evidence = combine_safe_results(request, results, safety, state)
        if safety["clinical_detected"]:
            return {**outcome, "decision": "escalate", "draft_response": draft}
        if results.get("task", {}).get("staged"):  # fixed notice: never the model's free text
            return {**outcome, **staged_reply(request, results, evidence, state)}
        verification = verify_response(request, draft, evidence, state)
    except BudgetExceeded:
        return {**outcome, "decision": "stop", "draft_response": BUDGET_MESSAGE}
    except Exception as exc:  # fail closed: never show the draft; log the class name only, never message or error text
        error_type = type(exc).__name__
        clinical = bool(outcome.get("safety", {}).get("clinical_detected"))
        if clinical:
            log.error("request_id=%s safety_gate=escalate outcome=escalation_failed error_type=%s", request_id, error_type)
        else:
            log.error("request_id=%s safety_gate=allow outcome=flow_failed error_type=%s", request_id, error_type)
        notice = ESCALATION_FAILED_NOTICE if clinical else escalation_notice(request)
        return {**outcome, "decision": "escalate", "draft_response": notice}
    citations = approved_sources(evidence)
    if verification.get("verification_status") != "PASS" or (evidence.strip() and not citations):
        return {**outcome, "decision": "escalate", "draft_response": escalation_notice(request),
                "verification": verification}  # withhold the draft
    return {**outcome, "decision": "allow", "draft_response": draft, "verification": verification,
            "citations": citations, "approved_phones": approved_phones(request, evidence)}


def staged_reply(request, results, evidence, state):
    """STAGED_NOTICE, after the verified retrieval answer if the request had one."""
    reply, citations = STAGED_NOTICE, []
    if "retrieval" in results and evidence.strip():
        info = "Approved Riverside Health information:\n" + narrowed_passage(request, evidence)
        sources = approved_sources(evidence)
        try:  # the refill is already staged: no failure here may hide that
            passed = bool(sources) and verify_response(request, info, evidence, state).get("verification_status") == "PASS"
            if passed:
                reply, citations = info + "\n\n" + STAGED_NOTICE, sources
            else:
                reply += " " + escalation_notice(request)  # opens the ticket, as on the normal path
        except BudgetExceeded:
            reply, citations = STAGED_NOTICE + " " + UNANSWERED_NOTICE, []
        except Exception:
            reply, citations = STAGED_NOTICE + " " + escalation_notice(request), []
    if any(k in request.lower() for k in OPERATIONAL_KEYWORDS):
        reply += " " + OTHER_REQUEST_NOTICE
    return {"decision": "allow", "draft_response": reply, "staged": True, "citations": citations}


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
