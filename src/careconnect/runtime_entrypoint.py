"""The one entry point the AgentCore runtime calls. All decisions are made by supervisor_flow."""

from careconnect.agents.supervisor_agent import api_result, supervisor_flow
from careconnect.supervisor import ESCALATION_FAILED_NOTICE


def invoke(payload):
    """Payload {"prompt": <request text>} -> {decision, reply, citations}."""
    request = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(request, str) or not request.strip():  # fail closed
        return api_result({"decision": "escalate", "draft_response": ESCALATION_FAILED_NOTICE})
    return api_result(supervisor_flow(request))
