#!/usr/bin/env bash
# Deploy CareConnect end to end: data, Bedrock, Lambda, Gateway stacks, the AgentCore runtime,
# the API stack, then the frontend with the API URL. Re-runs update in place.
# Usage: scripts/deploy.sh   (optional: PYDANTIC_LAYER_ARN=<pydantic v2 layer ARN for Python 3.12>)
# Remove everything with scripts/teardown.sh.
set -euo pipefail

REGION=us-east-1
TAGS=(Project=careconnect issue=125)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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

upload_code() { # lambda-dir-name -> s3 key
  python3 -m zipfile -c "$WORK/$1.zip" "$ROOT/Docs/Repo/lambda-functions/$1/lambda_function.py"
  aws s3 cp "$WORK/$1.zip" "s3://$BUCKET/code/$1.zip" --region "$REGION" >&2
  echo "code/$1.zip"
}

deploy careconnect-data careconnect-data.yaml
BUCKET=$(output careconnect-data ApprovedDocsBucketName)
bash "$ROOT/scripts/sync-approved-docs.sh" "$BUCKET" "$REGION"

deploy careconnect-bedrock careconnect-bedrock.yaml "ApprovedDocsBucketName=$BUCKET"
aws bedrock-agent start-ingestion-job --knowledge-base-id "$(output careconnect-bedrock KnowledgeBaseId)" \
  --data-source-id "$(output careconnect-bedrock DataSourceId)" --region "$REGION" >/dev/null

LAYER="PydanticLayerArn=${PYDANTIC_LAYER_ARN:-}"
deploy careconnect-lambdas careconnect-lambdas.yaml "CodeBucket=$BUCKET" "$LAYER" \
  "SafetyCodeKey=$(upload_code careconnect-deterministic-safety)" \
  "ToolsCodeKey=$(upload_code careconnect-mock-hospital-tools)"
deploy careconnect-gateway careconnect-gateway.yaml \
  "ToolsFunctionArn=$(output careconnect-lambdas ToolsFunctionArn)"

RUNTIME_ARN=$(bash "$ROOT/scripts/deploy-runtime.sh" careconnect-data careconnect-bedrock careconnect-gateway "$REGION")

# The API stack sets the proxy's ALLOWED_ORIGIN to its own CloudFront domain.
deploy careconnect-api careconnect-api.yaml "CodeBucket=$BUCKET" "$LAYER" \
  "ProxyCodeKey=$(upload_code careconnect-agentcore-proxy)" "AgentRuntimeArn=$RUNTIME_ARN"

API_URL=$(output careconnect-api ApiUrl)
mkdir -p "$WORK/frontend"
cp -R "$ROOT/src/frontend/." "$WORK/frontend/"
sed -E "s#API_URL: \"[^\"]*\"#API_URL: \"${API_URL}\"#" "$ROOT/src/frontend/config.js" > "$WORK/frontend/config.js"
aws s3 sync "$WORK/frontend" "s3://$(output careconnect-api FrontendBucketName)/" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$(output careconnect-api DistributionId)" --paths '/*' >/dev/null

echo "OK: https://$(output careconnect-api CloudFrontDomain) calls $API_URL"
