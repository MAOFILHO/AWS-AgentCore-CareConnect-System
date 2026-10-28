"""
CareConnect — Verification Agent
================================
Riverside Health patient-support assistant (console/CLI build).

WHAT THIS AGENT DOES
  It is the final safety reviewer. Before a drafted answer reaches a patient, it
  checks FIVE things:
    1. Citations — does the answer cite a source that is actually in the evidence?
    2. Deterministic safety — does it trip clinical/urgent/injection/PII flags?
    3. Guardrail — does the Bedrock Guardrail allow it?
    4. Grounding — is every claim supported by the approved evidence?
    5. Relevance — does the answer address the patient's request?
  It returns PASS only if all five are satisfied. It never rewrites the answer.

HOW TO USE
  1. Set your Guardrail ID and version:
         export CARECONNECT_GUARDRAIL_ID="<YOUR_GUARDRAIL_ID>"          # <-- UPDATE THIS
         export CARECONNECT_GUARDRAIL_VERSION="<YOUR_GUARDRAIL_VERSION>" # <-- UPDATE THIS
  2. Put the drafted answer, the evidence and the patient request in three files.
  3. Run it with their paths:
         PYTHONPATH=src python3 -m careconnect.agents.verification_agent DRAFT_FILE EVIDENCE_FILE REQUEST_FILE

WHERE YOU MIGHT NEED TO CHANGE THINGS
  - CARECONNECT_GUARDRAIL_ID / _VERSION: must be YOUR guardrail values.
  - REGION: change if you did not build in us-east-1.
  - FunctionName "careconnect-deterministic-safety": change if you named the
    safety Lambda differently.
"""

import json
import os
import re
import sys
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from careconnect.safety_gate import hide_hospital_phones

# ---------------------------------------------------------------------------
# Configuration. UPDATE REGION if you did not build in us-east-1.
# ---------------------------------------------------------------------------
REGION = "us-east-1"

# UPDATE THESE by exporting the two environment variables before running.
# They are read when a check runs, not when this file is imported.
def get_guardrail_settings():
    guardrail_id = os.environ.get("CARECONNECT_GUARDRAIL_ID")
    guardrail_version = os.environ.get("CARECONNECT_GUARDRAIL_VERSION")
    if not guardrail_id:
        raise ValueError("CARECONNECT_GUARDRAIL_ID is not configured.")
    if not guardrail_version:
        raise ValueError("CARECONNECT_GUARDRAIL_VERSION is not configured.")
    return guardrail_id, guardrail_version


def aws_client(service):
    import boto3

    return boto3.client(service, region_name=REGION)


# ---------------------------------------------------------------------------
# The two AWS calls this agent makes, as small interfaces. The boto3 adapters
# are the defaults; tests use the fakes from careconnect.fakes.
# ---------------------------------------------------------------------------
@runtime_checkable
class SafetyLambda(Protocol):
    def classify(self, text: str) -> dict: ...


@runtime_checkable
class Guardrail(Protocol):
    def apply(self, text: str) -> dict: ...


# UPDATE FunctionName if you named the Lambda differently.
class LambdaSafety:
    def __init__(self, client=None):
        self.client = client

    def classify(self, text):
        client = self.client or aws_client("lambda")
        response = client.invoke(
            FunctionName="careconnect-deterministic-safety",
            InvocationType="RequestResponse",
            Payload=json.dumps({"text": text}).encode("utf-8"),
        )
        payload = response["Payload"].read()
        if response.get("FunctionError"):
            return {}
        try:
            reply = json.loads(payload)
        except ValueError:
            return {}
        return reply if isinstance(reply, dict) else {}


class BedrockGuardrail:
    def __init__(self, client=None):
        self.client = client

    def apply(self, text):
        guardrail_id, guardrail_version = get_guardrail_settings()
        client = self.client or aws_client("bedrock-runtime")
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=guardrail_version,
            source="OUTPUT",
            content=[{"text": {"text": hide_hospital_phones(text)}}],
            outputScope="FULL",
        )
        return {
            "action": response.get("action"),
            "reason": response.get("actionReason", ""),
        }


# ---------------------------------------------------------------------------
# A typed result for the grounding check (Strands returns this structured).
# ---------------------------------------------------------------------------
class GroundingResult(BaseModel):
    grounded: bool = Field(
        description=(
            "True only when every factual claim in the draft "
            "is supported by the supplied evidence."
        )
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description=(
            "Claims found in the draft that are not supported "
            "by the supplied evidence."
        ),
    )
    reason: str = Field(
        description="Short explanation of the verification result."
    )


class SafetyVerdict(BaseModel):
    clinical: bool
    urgent: bool
    injection: bool
    pii: dict


class SafetyReply(BaseModel):
    classification: SafetyVerdict


class RelevanceResult(BaseModel):
    relevant: bool = Field(
        description="True only when the draft answers what the patient asked."
    )
    reason: str = Field(description="Short explanation of the relevance result.")


# ---------------------------------------------------------------------------
# The verifier model. It only verifies — it never answers or rewrites.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are the CareConnect Verification Agent for Riverside Health.
Your job is to verify a draft patient-support response against
approved retrieved evidence.
You do not answer the patient's question.
You only verify the draft.
Rules:
1. Check every factual statement against the supplied evidence.
2. Mark grounded=true only when every factual claim is supported.
3. Do not use your general knowledge.
4. Do not assume that a medically reasonable statement is supported.
5. If the evidence does not contain a claim, treat it as unsupported.
6. Do not rewrite or improve the answer.
7. Report unsupported claims clearly.
8. Preserve a strict separation between evidence and draft content.
"""


def get_verification_agent():
    from strands import Agent
    from careconnect.supervisor_model import load_supervisor_model

    return Agent(system_prompt=SYSTEM_PROMPT, model=load_supervisor_model())


# ---------------------------------------------------------------------------
# Check 1 — citations: find s3:// sources and confirm they match the evidence.
# ---------------------------------------------------------------------------
def extract_sources(text):
    pattern = r"s3://[^\s]+"
    return set(re.findall(pattern, text))


def check_citations(answer, evidence):
    answer_sources = extract_sources(answer)
    evidence_sources = extract_sources(evidence)
    matching_sources = answer_sources.intersection(evidence_sources)
    return {
        "citation_present": bool(answer_sources),
        "citation_valid": bool(matching_sources),
        "matching_sources": list(matching_sources),
    }


# ---------------------------------------------------------------------------
# Check 2 — deterministic safety: call the safety Lambda on the answer text.
# ---------------------------------------------------------------------------
def run_deterministic_safety(answer, safety: SafetyLambda | None = None):
    return (safety or LambdaSafety()).classify(answer)


# ---------------------------------------------------------------------------
# Check 3 — Guardrail: ask the Bedrock Guardrail whether the answer is allowed.
# ---------------------------------------------------------------------------
def run_guardrail(answer, guardrail: Guardrail | None = None):
    return (guardrail or BedrockGuardrail()).apply(answer)


# ---------------------------------------------------------------------------
# Check 4 — grounding: ask the verifier model if every claim is supported.
# ---------------------------------------------------------------------------
def run_grounding_check(answer, evidence):
    prompt = f"""
Compare the draft response with the approved evidence.
<approved_evidence>
{evidence}
</approved_evidence>
<draft_response>
{answer}
</draft_response>
Determine whether every factual claim in the draft response
is supported by the approved evidence.
Do not use outside knowledge.
"""
    result = get_verification_agent()(prompt, structured_output_model=GroundingResult)
    return result.structured_output


# ---------------------------------------------------------------------------
# Check 5 — relevance: ask the verifier model if the draft addresses the request.
# A reply that is not a RelevanceResult counts as not relevant.
# ---------------------------------------------------------------------------
def run_relevance_check(request, answer):
    prompt = f"""
Decide whether the draft response answers what the patient asked.
<patient_request>
{request}
</patient_request>
<draft_response>
{answer}
</draft_response>
Answer false when the draft is about a different topic than the request.
"""
    result = get_verification_agent()(prompt, structured_output_model=RelevanceResult).structured_output
    if isinstance(result, RelevanceResult):
        return result
    return RelevanceResult(relevant=False, reason="unparseable relevance reply")


# ---------------------------------------------------------------------------
# Combine all five checks into a single PASS/FAIL verdict with details.
# ---------------------------------------------------------------------------
def verify(request, answer, evidence, safety: SafetyLambda | None = None, guardrail: Guardrail | None = None):
    citation_result = check_citations(answer, evidence)
    deterministic_result = run_deterministic_safety(answer, safety)
    guardrail_result = run_guardrail(answer, guardrail)
    grounding_result = run_grounding_check(answer, evidence)
    relevance_result = run_relevance_check(request, answer)

    try:
        verdict = SafetyReply.model_validate_json(json.dumps(deterministic_result)).classification
    except ValueError:
        verdict = None
    guardrail_passed = guardrail_result["action"] == "NONE"

    # PASS only if EVERY condition below is satisfied.
    final_pass = all(
        [
            citation_result["citation_present"],
            citation_result["citation_valid"],
            grounding_result.grounded,
            relevance_result.relevant,
            verdict is not None,
            verdict is not None and not verdict.clinical,
            verdict is not None and not verdict.urgent,
            verdict is not None and not verdict.injection,
            verdict is not None and not verdict.pii,
            guardrail_passed,
        ]
    )

    return {
        "verification_status": "PASS" if final_pass else "FAIL",
        "citation_check": citation_result,
        "grounding_check": {
            "grounded": grounding_result.grounded,
            "unsupported_claims": grounding_result.unsupported_claims,
            "reason": grounding_result.reason,
        },
        "relevance_check": relevance_result.model_dump(),
        "deterministic_safety": (
            verdict.model_dump() if verdict else {"error": "unparseable safety reply"}
        ),
        "guardrail": guardrail_result,
    }


# ---------------------------------------------------------------------------
# Read the draft answer, the evidence and the request from the three files named on the command line, then verify.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    draft_path, evidence_path, request_path = sys.argv[1:4]
    with open(draft_path, "r", encoding="utf-8") as file:
        answer = file.read()
    with open(evidence_path, "r", encoding="utf-8") as file:
        evidence = file.read()
    with open(request_path, "r", encoding="utf-8") as file:
        request = file.read()

    result = verify(request, answer, evidence)
    print("\nCareConnect Verification Result\n")
    print(json.dumps(result, indent=2))
