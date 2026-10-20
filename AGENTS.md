# AWS-AgentCore-CareConnect-System

Instructions for every agent that works in this repo. Keep it short and true;
every factory agent reads it before touching code.

## What this is
<!-- one paragraph: what the product does, who uses it -->

## Key paths
- `src/` application code
- `test/` tests (one file per module)

## Setup (fresh checkout)
```bash
npm ci || npm install
```

## Dev server
```bash
PORT=${PORT:-3000} npm run dev
```

## Checks
Run all of these before every commit. They must pass. Never skip or weaken a test to make them pass.
```bash
npm test
npm run typecheck --if-present
npm run lint --if-present
npm run build --if-present
```

## Conventions
- Node.js, ES modules (`"type": "module"`), no CommonJS.
- Smallest change that meets the issue. No speculative options.
- One commit per piece of work, one-line message.

<!-- factory:start -->
## Software factory

This repo is built partly by a software factory (Sandcastle + GitHub Actions).

- Issues labelled `factory` are picked up by `factory run`. Each gets one container, one branch `sandcastle/issue-<n>`, one PR.
- A code reviewer and a security reviewer run on every branch and every PR. A security `blocker` stops the merge.
- Agents never merge. Branch protection requires one human approval and green checks.
- `REVIEW.md` holds reviewer conventions; the daily `factory-improve` workflow proposes edits to it through a PR.
- Write issues with 2–5 checkable acceptance criteria; one issue = one PR under ~400 changed lines.
- Agent rules: never build on `main`; one worktree and branch per task; never force-push except `--force-with-lease` on your own branch; never read `.env` or dump the environment.
<!-- factory:end -->
