#!/usr/bin/env bash
# Remove what scripts/deploy.sh created: empty the buckets, delete the stacks in reverse order.
# Usage: scripts/teardown.sh
# The AgentCore runtime is not a stack: remove it with 'agentcore destroy'.
set -euo pipefail

REGION=us-east-1

empty() { # stack output-key
  local b
  b=$(aws cloudformation describe-stacks --stack-name "$1" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || true)
  if [ -n "$b" ] && [ "$b" != "None" ]; then aws s3 rm "s3://$b" --recursive --region "$REGION"; fi
}

delete() { # stack
  aws cloudformation delete-stack --stack-name "$1" --region "$REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$1" --region "$REGION"
  echo "OK: deleted $1"
}

empty careconnect-api FrontendBucketName
delete careconnect-api
delete careconnect-gateway
delete careconnect-lambdas
delete careconnect-bedrock
empty careconnect-data ApprovedDocsBucketName
delete careconnect-data
