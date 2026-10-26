# Staging reaches main only through a promotion PR the owner merges

All factory and super-board work merges into `staging`. `main` must stay deployable, so it changes only through a promotion: the owner starts the `promote` workflow (`.github/workflows/promote.yml`) by hand. It runs every check in AGENTS.md on `staging`, the golden scenarios included, and opens one `staging` to `main` PR only when all of them pass. It never pushes to `main`. The owner merges that PR with `bash .sandcastle/merge.sh <pr>`. No agent, Action or merge gate merges into `main`.

We chose a manual trigger over a schedule or a push trigger so that a promotion is always a decision. The repo is on GitHub Free, so branch protection is not enforced and this rule holds by convention.

## Consequences

- The deploy smoke test stays manual. `scripts/smoke.sh` needs a deployed API and AWS credentials, which the workflow does not have. Before merging, the owner deploys `staging` with `scripts/deploy.sh` and runs `scripts/smoke.sh <api-url>`; a failure means no merge.
- A PR opened with the workflow's `GITHUB_TOKEN` does not start other workflows, so `factory-ci` does not run on the promotion PR at first, and `merge.sh` refuses a PR with no checks. The owner closes and reopens the PR once; that starts `factory-ci` on its head, and `merge.sh` merges only when those checks are green.
- GitHub dispatches a workflow only from the default branch, so `promote` cannot run until `promote.yml` is on `main`. The first promotion is a `staging` to `main` PR the owner opens by hand, under the same checks and smoke test.
- If a promotion PR is already open, the workflow does not open a second one.
- The `factory-merge` Action never merges the promotion PR: its branch is `staging`, not `sandcastle/*`.
