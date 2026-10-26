#!/usr/bin/env bash
# Empty the approved-docs bucket, then delete the data stack.
# Usage: scripts/destroy-data-stack.sh <stack-name> [region]
set -euo pipefail

STACK="${1:?usage: $0 <stack-name> [region]}"
REGION="${2:-us-east-1}"

bucket=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApprovedDocsBucketName'].OutputValue" --output text)
if [ -n "$bucket" ] && [ "$bucket" != "None" ]; then
  aws s3 rm "s3://$bucket" --recursive --region "$REGION"
fi
aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION"
echo "OK: deleted $STACK"
