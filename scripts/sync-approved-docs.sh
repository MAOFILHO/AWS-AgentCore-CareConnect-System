#!/usr/bin/env bash
# Upload the approved documents to s3://<bucket>/approved/ and fail if the counts differ.
# Usage: scripts/sync-approved-docs.sh <bucket-name> [region]
set -euo pipefail

BUCKET="${1:?usage: $0 <bucket-name> [region]}"
REGION="${2:-us-east-1}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/Docs/Repo/careconnect-approved-docs/approved"

local_count=$(find "$SRC" -type f ! -name ".*" | wc -l | tr -d ' ')
aws s3 sync "$SRC" "s3://$BUCKET/approved/" --delete --exclude ".*" --exclude "*/.*" --region "$REGION"
remote_count=$(aws s3 ls "s3://$BUCKET/approved/" --recursive --region "$REGION" | wc -l | tr -d ' ')

if [[ "$local_count" != "$remote_count" ]]; then
  echo "FAIL: $local_count local files, $remote_count objects in s3://$BUCKET/approved/" >&2
  exit 1
fi
echo "OK: $remote_count files in s3://$BUCKET/approved/"
