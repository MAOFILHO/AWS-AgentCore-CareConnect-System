#!/usr/bin/env bash
# Merge one factory PR once every check is green. The owner or an agent in a session the owner started runs it; the factory builder and reviewer never do.
#   bash .sandcastle/merge.sh <pr-number>
set -euo pipefail

pr="${1:-}"
[ -n "$pr" ] || { echo "Usage: bash .sandcastle/merge.sh <pr-number>" >&2; exit 1; }

info="$(gh pr view "$pr" --json headRefName,isDraft,labels,headRefOid \
  -q '[.headRefName, .isDraft, ([.labels[].name] | index("needs-human") != null), .headRefOid] | @tsv')"
IFS=$'\t' read -r head draft needs_human sha <<<"$info"

case "$head" in
  sandcastle/*) ;;
  *) echo "PR #$pr is not a factory PR (branch $head)." >&2; exit 1 ;;
esac

# A security blocker leaves the PR as a draft with the needs-human label, even when every check is green.
if [ "$draft" = "true" ] || [ "$needs_human" = "true" ]; then
  echo "PR #$pr is a draft or labelled needs-human: it has an open security blocker or needs a human. Not merging." >&2
  exit 1
fi

# gh pr checks exits non-zero while any check fails or is pending, so ignore its exit code and read the table.
checks="$(gh pr checks "$pr" || true)"
bad="$(awk -F'\t' '$2 != "pass" { print "  " $1 ": " $2 }' <<<"$checks")"
if [ -z "$checks" ] || [ -n "$bad" ]; then
  printf 'Checks not green on PR #%s:\n%s\n' "$pr" "${bad:-  no checks reported}" >&2
  exit 1
fi

[ -n "$sha" ] || { echo "PR #$pr has no head commit (headRefOid is empty). Not merging." >&2; exit 1; }

# Refuses the merge if the branch moved since the checks were read.
gh pr merge "$pr" --merge --match-head-commit "$sha"
echo "merged PR #$pr"
