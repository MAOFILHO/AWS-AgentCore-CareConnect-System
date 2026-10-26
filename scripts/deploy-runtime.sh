#!/usr/bin/env bash
# Deploy the Supervisor to AgentCore Runtime with the five CARECONNECT_* values read from stack outputs,
# then let its execution role call the Knowledge Base, the approval workflow, the Gateway and the escalations table.
# Usage: scripts/deploy-runtime.sh [data-stack] [bedrock-stack] [gateway-stack] [region]
# agentcore reads .bedrock_agentcore.yaml from the repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA_STACK="${1:-careconnect-data}"
BEDROCK_STACK="${2:-careconnect-bedrock}"
GATEWAY_STACK="${3:-careconnect-gateway}"
REGION="${4:-us-east-1}"
AGENT="${AGENT:-careconnectsupervisor}"

output() { # stack key
  aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || true
}

CARECONNECT_KB_ID=$(output "$BEDROCK_STACK" KnowledgeBaseId)
CARECONNECT_GATEWAY_URL=$(output "$GATEWAY_STACK" GatewayUrl)
CARECONNECT_GUARDRAIL_ID=$(output "$BEDROCK_STACK" GuardrailId)
CARECONNECT_GUARDRAIL_VERSION=$(output "$BEDROCK_STACK" GuardrailVersion)
CARECONNECT_STATE_MACHINE_ARN=$(output "$DATA_STACK" ApprovalWorkflowArn)
GATEWAY_ID=$(output "$GATEWAY_STACK" GatewayId)
ESCALATIONS_TABLE=$(output "$DATA_STACK" EscalationsTableName)

for v in CARECONNECT_KB_ID CARECONNECT_GATEWAY_URL CARECONNECT_GUARDRAIL_ID \
         CARECONNECT_GUARDRAIL_VERSION CARECONNECT_STATE_MACHINE_ARN GATEWAY_ID ESCALATIONS_TABLE; do
  if [ -z "${!v}" ] || [ "${!v}" = "None" ]; then
    echo "ERROR: $v is empty" >&2
    exit 1
  fi
done

out=$(agentcore deploy --agent "$AGENT" --auto-update-on-conflict \
  --env "CARECONNECT_KB_ID=$CARECONNECT_KB_ID" \
  --env "CARECONNECT_GATEWAY_URL=$CARECONNECT_GATEWAY_URL" \
  --env "CARECONNECT_GUARDRAIL_ID=$CARECONNECT_GUARDRAIL_ID" \
  --env "CARECONNECT_GUARDRAIL_VERSION=$CARECONNECT_GUARDRAIL_VERSION" \
  --env "CARECONNECT_STATE_MACHINE_ARN=$CARECONNECT_STATE_MACHINE_ARN")
echo "$out" >&2

# The deploy output wraps the ARN across lines, so ask the service for it.
arn=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
  --query "agentRuntimes[?agentRuntimeName=='$AGENT'].agentRuntimeArn | [0]" --output text 2>/dev/null || true)
if [ -z "$arn" ] || [ "$arn" = "None" ]; then
  echo "ERROR: no runtime named $AGENT in list-agent-runtimes" >&2
  exit 1
fi
# agentcore deploy has no tag option; tag the runtime it created.
aws bedrock-agentcore-control tag-resource --resource-arn "$arn" --region "$REGION" \
  --tags Project=careconnect,issue=152 >&2

# The toolkit's execution role only allows model calls; grant the four calls the flow makes.
account=$(echo "$arn" | cut -d: -f5)
role_arn=$(aws bedrock-agentcore-control get-agent-runtime --region "$REGION" \
  --agent-runtime-id "${arn##*/}" --query roleArn --output text)
role="${role_arn##*/}"
policy=$(cat <<JSON
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": "bedrock:Retrieve",
   "Resource": "arn:aws:bedrock:$REGION:$account:knowledge-base/$CARECONNECT_KB_ID"},
  {"Effect": "Allow", "Action": "states:StartExecution",
   "Resource": "$CARECONNECT_STATE_MACHINE_ARN"},
  {"Effect": "Allow", "Action": "bedrock-agentcore:InvokeGateway",
   "Resource": "arn:aws:bedrock-agentcore:$REGION:$account:gateway/$GATEWAY_ID"},
  {"Effect": "Allow", "Action": "dynamodb:PutItem",
   "Resource": "arn:aws:dynamodb:$REGION:$account:table/$ESCALATIONS_TABLE"}
]}
JSON
)
aws iam put-role-policy --role-name "$role" --policy-name careconnect-runtime-access \
  --policy-document "$policy" >&2
aws iam tag-role --role-name "$role" \
  --tags Key=Project,Value=careconnect Key=issue,Value=156 >&2
echo "$arn"
