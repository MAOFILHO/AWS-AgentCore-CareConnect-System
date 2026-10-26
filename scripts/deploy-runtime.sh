#!/usr/bin/env bash
# Read the five CARECONNECT_* values from stack outputs and deploy the Supervisor to
# AgentCore Runtime. Run it from the agentcore project folder (agentcore configure done).
# Usage: scripts/deploy-runtime.sh <data-stack> <bedrock-stack> <gateway-stack> [region]
set -euo pipefail

DATA="${1:?usage: $0 <data-stack> <bedrock-stack> <gateway-stack> [region]}"
BEDROCK="${2:?usage: $0 <data-stack> <bedrock-stack> <gateway-stack> [region]}"
GATEWAY="${3:?usage: $0 <data-stack> <bedrock-stack> <gateway-stack> [region]}"
REGION="${4:-us-east-1}"

output() {
  aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

CARECONNECT_KB_ID=$(output "$BEDROCK" KnowledgeBaseId)
CARECONNECT_GATEWAY_URL=$(output "$GATEWAY" GatewayUrl)
CARECONNECT_GUARDRAIL_ID=$(output "$BEDROCK" GuardrailId)
CARECONNECT_GUARDRAIL_VERSION=$(output "$BEDROCK" GuardrailVersion)
CARECONNECT_STATE_MACHINE_ARN=$(output "$DATA" ApprovalWorkflowArn)

envs=()
for name in CARECONNECT_KB_ID CARECONNECT_GATEWAY_URL CARECONNECT_GUARDRAIL_ID \
  CARECONNECT_GUARDRAIL_VERSION CARECONNECT_STATE_MACHINE_ARN; do
  value="${!name}"
  if [[ -z "$value" || "$value" == "None" ]]; then
    echo "FAIL: $name is empty; check the stack outputs" >&2
    exit 1
  fi
  envs+=(--env "$name=$value")
done
echo "Gateway URL: $CARECONNECT_GATEWAY_URL"

export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=3072}"
log=$(mktemp)
trap 'rm -f "$log"' EXIT
agentcore deploy "${envs[@]}" | tee "$log"

arn=$(grep -oE "arn:aws:bedrock-agentcore:[^:]+:[0-9]+:runtime/[A-Za-z0-9_-]+" "$log" | tail -1 || true)
if [[ -z "$arn" ]]; then
  echo "FAIL: no runtime ARN in the agentcore deploy output" >&2
  exit 1
fi
echo "Runtime ARN: $arn"
