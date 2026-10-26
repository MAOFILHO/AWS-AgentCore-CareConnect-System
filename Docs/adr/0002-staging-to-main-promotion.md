# Staging reaches main only through a promotion PR the owner merges

All factory and super-board work merges into `staging`. `main` must stay deployable, so it changes only through a promotion: the owner starts the `promote` workflow (`.github/workflows/promote.yml`) by hand. It runs every check in AGENTS.md on `staging`, the golden scenarios included. Only when all of them pass does it write the checked `staging` commit and the `main...<sha>` compare URL to the job summary. It never pushes to `main` and never opens a PR. The owner opens one `staging` to `main` PR from that summary (the session supervising the factory may do this for the owner) and merges it with `bash .sandcastle/merge.sh <pr>`. No agent, Action or merge gate merges into `main`.

We chose a manual trigger over a schedule or a push trigger so that a promotion is always a decision. The repo is on GitHub Free, so branch protection is not enforced and this rule holds by convention.

## Consequences

- The deploy smoke test stays manual. `scripts/smoke.sh` needs a deployed API and AWS credentials, which the workflow does not have. Before merging, the owner deploys `staging` with `scripts/deploy.sh` and runs `scripts/smoke.sh <api-url>`; a failure means no merge.
- The workflow does not open the PR because this repo does not let Actions create pull requests (`can_approve_pull_request_reviews` is `false` in the Actions settings), and we keep that setting off. A PR the owner opens starts `factory-ci` as usual, and `merge.sh` merges only when those checks are green.
- The owner opens the PR only while `staging` is still at the commit the summary names. If `staging` moved, run `promote` again.
- GitHub dispatches a workflow only from the default branch, so `promote` cannot run until `promote.yml` is on `main`. The first promotion is a `staging` to `main` PR the owner opens by hand, under the same checks and smoke test.
- If a promotion PR is already open, the owner does not open a second one.
- The `factory-merge` Action never merges the promotion PR: its branch is `staging`, not `sandcastle/*`.
