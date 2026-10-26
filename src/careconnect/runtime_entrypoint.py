"""The one entry point the AgentCore runtime calls. All decisions are made by supervisor_flow."""

import sys
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp

# The runtime runs this file as a script, so put the package root (src/) on the path first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from careconnect.agents.supervisor_agent import api_result, supervisor_flow
from careconnect.supervisor import ESCALATION_FAILED_NOTICE

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    """Payload {"prompt": <request text>} -> {decision, reply, citations, staged}."""
    request = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(request, str) or not request.strip():  # fail closed
        return api_result({"decision": "escalate", "draft_response": ESCALATION_FAILED_NOTICE})
    return api_result(supervisor_flow(request))


if __name__ == "__main__":
    app.run()
