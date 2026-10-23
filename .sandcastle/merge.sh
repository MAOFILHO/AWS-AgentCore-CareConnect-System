#!/usr/bin/env bash
# Merge one factory PR once every check is green. You run it, so you are the approval.
#   bash .sandcastle/merge.sh <pr-number>
set -euo pipefail

pr="${1:-}"
[ -n "$pr" ] || { echo "Usage: bash .sandcastle/merge.sh <pr-number>" >&2; exit 1; }

head="$(gh pr view "$pr" --json headRefName -q .headRefName)"
case "$head" in
  sandcastle/*) ;;
  *) echo "PR #$pr is not a factory PR (branch $head)." >&2; exit 1 ;;
esac

bad="$(gh pr checks "$pr" | awk -F'\t' '$2 != "pass" { print "  " $1 ": " $2 }')"
if [ -n "$bad" ]; then
  printf 'Checks not green on PR #%s:\n%s\n' "$pr" "$bad" >&2
  exit 1
fi

gh pr merge "$pr" --merge
echo "merged PR #$pr"
