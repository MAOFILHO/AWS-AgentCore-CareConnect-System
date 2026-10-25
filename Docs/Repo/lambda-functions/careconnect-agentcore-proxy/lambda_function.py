"""
CareConnect — AgentCore Proxy Lambda (with CORS)
================================================
Riverside Health patient-support assistant (console/CLI build).

WHAT THIS LAMBDA DOES
  It sits between the public API Gateway and the deployed Supervisor runtime.
  It receives a web request { "prompt": "..." }, calls the AgentCore runtime,
  reads the {decision, reply, citations} result, and returns it with the
  CORS headers a browser needs. Failures return a short fixed error message only.

HOW TO DEPLOY (console)
  1. AWS Lambda → Create function → name it:  careconnect-agentcore-proxy
     Runtime: Python 3.12.
  2. Paste this file into lambda_function.py.
  3. >>> EDIT the three CHANGE markers below (your runtime ARN, region, origin).
  4. Deploy.
  5. Give the Lambda's execution role permission to call the runtime
     (bedrock-agentcore:InvokeAgentRuntime).
  6. Connect it to an API Gateway POST /careconnect route.
  7. Add pydantic (v2) to the function through a layer or the deploy package.

>>> THINGS YOU MUST UPDATE ARE MARKED "CHANGE #" BELOW <<<
"""

# ===========================================================================
# >>> CHANGE #1: Add YOUR real AgentCore runtime ARN (from the deploy step).
#     It looks like:
#     arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/<runtime-id>
# ===========================================================================
AGENT_RUNTIME_ARN = "REPLACE_ME_WITH_YOUR_AGENT_RUNTIME_ARN"

# >>> CHANGE #2: region (leave as-is if your agent is in us-east-1).
AWS_REGION = "us-east-1"

# >>> CHANGE #3: your CloudFront domain, e.g. "https://dxxxx.cloudfront.net".
#     Only this origin gets a CORS allowance. Never use "*".
ALLOWED_ORIGIN = "REPLACE_ME_WITH_YOUR_WEBSITE_ORIGIN"

import json
import re

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr
from typing import Literal


# Same contract as careconnect.api_reply.ApiReply (this Lambda deploys alone).
class ApiReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "escalate", "block", "stop"]
    reply: StrictStr
    citations: list[StrictStr]
    staged: StrictBool = False


# Build the CORS headers. The allow-origin header is added only when the
# caller's Origin is the one configured website.
def _headers(event):
    headers = {"Content-Type": "application/json"}
    origin = (event.get("headers") or {}).get("origin") or (
        event.get("headers") or {}
    ).get("Origin")
    if origin and origin == ALLOWED_ORIGIN:
        headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        headers["Access-Control-Allow-Headers"] = "Content-Type"
        headers["Access-Control-Allow-Methods"] = "OPTIONS,POST"
        headers["Vary"] = "Origin"
    return headers


# Small helper to build a JSON response with the CORS headers attached.
def _reply(event, status, obj):
    return {"statusCode": status, "headers": _headers(event), "body": json.dumps(obj)}


def _client():
    import boto3

    return boto3.client("bedrock-agentcore", region_name=AWS_REGION)


# Remove any <thinking>...</thinking> blocks from the model's text.
def _clean(full_text):
    return re.sub(
        r"<thinking\b[^>]*>.*?</thinking>", "", full_text, flags=re.DOTALL
    ).strip()


# The runtime streams its answer as "server-sent events" (SSE). This pulls the
# text pieces out of that stream and joins them into one string.
def _extract_text_from_sse(raw):
    pieces = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            evt = json.loads(line[5:].strip())
        except ValueError:
            continue
        text = (
            evt.get("event", {})
            .get("contentBlockDelta", {})
            .get("delta", {})
            .get("text")
        )
        if text:
            pieces.append(text)
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Lambda entry point.
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    # Handle the browser's CORS preflight (OPTIONS) request first.
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": _headers(event), "body": ""}

    # Read the prompt out of the request body.
    try:
        body = event.get("body") or "{}"
        body = json.loads(body) if isinstance(body, str) else body
        prompt = (body.get("prompt") or "").strip()
    except Exception:
        return _reply(event, 400, {"error": "Bad request body."})

    if not prompt:
        return _reply(event, 400, {"error": "Missing 'prompt'."})

    # Any failure returns a short fixed message: no trace, no diagnostics.
    try:
        response = _client().invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            payload=json.dumps({"prompt": prompt}).encode("utf-8"),
        )
        raw_bytes = response["response"].read()
        raw = (
            raw_bytes.decode("utf-8")
            if isinstance(raw_bytes, (bytes, bytearray))
            else str(raw_bytes)
        )
    except Exception:
        return _reply(event, 500, {"error": "Request failed."})

    # The runtime returns {decision, reply, citations}. Any other shape is the fixed error.
    try:
        result = ApiReply.model_validate_json(_clean(_extract_text_from_sse(raw)) or _clean(raw))
    except Exception:
        return _reply(event, 500, {"error": "Request failed."})
    return _reply(event, 200, result.model_dump())
