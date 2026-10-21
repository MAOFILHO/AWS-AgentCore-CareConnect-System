"""Verification: citation, grounding, PII and Guardrail checks on a draft reply."""

from typing import Literal

from pydantic import BaseModel

from careconnect.safety_gate import find_pii


class VerificationResult(BaseModel):
    status: Literal["PASS", "FAIL", "ERROR", "SKIPPED"]
    reason: str = ""


def verify(draft, citations, passages, grounding, guardrail):
    """PASS only if every check passes. Any other outcome, including an error, is not PASS."""
    if not citations or any(name not in passages for name in citations):
        return VerificationResult(status="FAIL", reason="citation")
    if find_pii(draft):
        return VerificationResult(status="FAIL", reason="pii")
    try:
        if not grounding.check(draft, [passages[name] for name in citations]):
            return VerificationResult(status="FAIL", reason="grounding")
        if not guardrail.check(draft):
            return VerificationResult(status="FAIL", reason="guardrail")
    except Exception:
        return VerificationResult(status="ERROR", reason="check unavailable")
    return VerificationResult(status="PASS")
