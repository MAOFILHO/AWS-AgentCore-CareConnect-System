#!/usr/bin/env bash
# Deploy CareConnect end to end: data, Bedrock, Lambda, Gateway stacks, the AgentCore runtime,
# the API stack, then the frontend with the API URL. Re-runs update in place.
# Usage: scripts/deploy.sh   (optional: PYDANTIC_LAYER_ARN=<pydantic v2 layer ARN for Python 3.12>)
# Remove everything with scripts/teardown.sh.
set -euo pipefail

REGION=us-east-1
TAGS=(Project=careconnect issue=125)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" # agentcore reads the project from the cwd
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

deploy() { # stack template [Key=Value ...]
  local stack="$1" template="$2"; shift 2
  local params=(); [ $# -gt 0 ] && params=(--parameter-overrides "$@")
  aws cloudformation deploy --stack-name "$stack" --region "$REGION" \
    --template-file "$ROOT/infra/$template" --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset --tags "${TAGS[@]}" ${params[@]+"${params[@]}"}
}

output() { # stack key
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text)
  if [ -z "$v" ] || [ "$v" = "None" ]; then echo "ERROR: $1 has no output $2" >&2; exit 1; fi
  echo "$v"
}

upload_code() { # lambda-dir-name -> s3 key, named by content hash so a code change changes S3Key
  local src="$ROOT/Docs/Repo/lambda-functions/$1/lambda_function.py" key
  key="code/$1-$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()[:12])' "$src").zip"
  python3 -m zipfile -c "$WORK/$1.zip" "$src"
  aws s3 cp "$WORK/$1.zip" "s3://$BUCKET/$key" --region "$REGION" >&2
  echo "$key"
}

deploy careconnect-data careconnect-data.yaml
BUCKET=$(output careconnect-data ApprovedDocsBucketName)
bash "$ROOT/scripts/sync-approved-docs.sh" "$BUCKET" "$REGION"

GUARDRAIL_HASH=$(python3 "$ROOT/scripts/guardrail_hash.py" "$ROOT/infra/careconnect-bedrock.yaml")
deploy careconnect-bedrock careconnect-bedrock.yaml "ApprovedDocsBucketName=$BUCKET" \
  "GuardrailHash=$GUARDRAIL_HASH"
# Assign each output or code key on its own line: an exit inside $(...) in an argument is ignored.
KB_ID=$(output careconnect-bedrock KnowledgeBaseId)
DS_ID=$(output careconnect-bedrock DataSourceId)
aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
  --region "$REGION" >/dev/null

LAYER="PydanticLayerArn=${PYDANTIC_LAYER_ARN:-}"
SAFETY_KEY=$(upload_code careconnect-deterministic-safety)
TOOLS_KEY=$(upload_code careconnect-mock-hospital-tools)
deploy careconnect-lambdas careconnect-lambdas.yaml "CodeBucket=$BUCKET" "$LAYER" \
  "SafetyCodeKey=$SAFETY_KEY" "ToolsCodeKey=$TOOLS_KEY"
TOOLS_ARN=$(output careconnect-lambdas ToolsFunctionArn)
deploy careconnect-gateway careconnect-gateway.yaml "ToolsFunctionArn=$TOOLS_ARN"

RUNTIME_ARN=$(bash "$ROOT/scripts/deploy-runtime.sh" careconnect-data careconnect-bedrock careconnect-gateway "$REGION")

# The API stack sets the proxy's ALLOWED_ORIGIN to its own CloudFront domain.
PROXY_KEY=$(upload_code careconnect-agentcore-proxy)
deploy careconnect-api careconnect-api.yaml "CodeBucket=$BUCKET" "$LAYER" \
  "ProxyCodeKey=$PROXY_KEY" "AgentRuntimeArn=$RUNTIME_ARN"

API_URL=$(output careconnect-api ApiUrl)
mkdir -p "$WORK/frontend"
cp -R "$ROOT/src/frontend/." "$WORK/frontend/"
sed -E "s#API_URL: \"[^\"]*\"#API_URL: \"${API_URL}\"#" "$ROOT/src/frontend/config.js" > "$WORK/frontend/config.js"
WEB_BUCKET=$(output careconnect-api FrontendBucketName)
DIST_ID=$(output careconnect-api DistributionId)
DOMAIN=$(output careconnect-api CloudFrontDomain)
aws s3 sync "$WORK/frontend" "s3://$WEB_BUCKET/" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' >/dev/null

echo "OK: https://$DOMAIN calls $API_URL"
