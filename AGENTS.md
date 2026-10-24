# AWS-AgentCore-CareConnect-System

Instructions for every agent that works in this repo. Keep it short and true;
every factory agent reads it before touching code.

## What this is
CareConnect is a patient-support assistant for the fictional Riverside Health hospital network. Patients ask routine questions and get cited answers from approved documents. Clinical questions go to a licensed clinician. See `GLOSSARY.md` for the terms.

## Key paths
- `src/` application code
- `test/` tests (one file per module)

## Setup (fresh checkout)
```bash
npm ci || npm install
python3 -m pip install -r requirements.txt
```

## Dev server
```bash
PORT=${PORT:-3000} npm run dev
```

## Checks
Run all of these before every commit. They must pass. Never skip or weaken a test to make them pass.
```bash
npm test
PYTHONPATH=src python3 -m unittest discover -s test
npm run typecheck --if-present
npm run lint --if-present
npm run build --if-present
```

## Conventions
- Agents and Lambdas are Python (Strands and AgentCore SDKs). Node stays for the frontend and factory tooling, as ES modules only.
- Every structured output of an agent or a Lambda (a Safety gate decision, a Verification result, an API reply body) is a Pydantic model. Parse model replies with `model_validate_json` and treat a parse failure as FAIL, never as PASS. Add `pydantic` to the Python requirements in the first ticket that needs it.
- Smallest change that meets the issue. No speculative options.
- Use the words in `GLOSSARY.md`. "Agent" means one of the six LLM agents; the Safety gate is code.
- One commit per piece of work, one-line message.

## Safety rules
- Fail closed: if the Safety gate cannot decide whether a request is clinical, escalate. Never answer.
- Answers come only from `approved/` documents, with citations. Files in `evaluation-untrusted/` are test inputs only.
- Every safety bug adds one golden scenario. All golden scenarios must pass; there is no pass-rate threshold.
- Logs hold the request ID, the Safety gate decision and the outcome. Never log patient message text.
- Put each AWS service behind a small interface with an in-memory fake. Tests use the fakes.
- Supervisor limits (8 steps, $0.05, 30 seconds) are config values.

## AWS and cost
See `Docs/adr/0001-factory-aws-access-capped-account.md`. Use the lowest-cost option or Free Tier. Never add a NAT Gateway, a provisioned search cluster or provisioned concurrency. Tag every resource with the issue number and destroy it when the PR closes.

<!-- factory:start -->
## Software factory

This repo is built partly by a software factory (Sandcastle + GitHub Actions).

- Issues labelled `factory` are picked up by `factory run`. Each gets one container, one branch `sandcastle/issue-<n>`, one PR.
- A code reviewer and a security reviewer run on every branch and every PR. A security `blocker` stops the merge.
- Agents never merge. This repo is on GitHub Free, so branch protection is not enforced. A human confirms every check is green and approves before merging.
- A human merges a factory PR with `bash .sandcastle/merge.sh <pr>`. It refuses a draft, a `needs-human` PR and any check that is not green.
- `REVIEW.md` holds reviewer conventions; the daily `factory-improve` workflow proposes edits to it through a PR.
- Write issues with 2–5 checkable acceptance criteria; one issue = one PR under ~400 changed lines.
- Agent rules: never build on `main`; one worktree and branch per task; never force-push except `--force-with-lease` on your own branch; never read `.env` or dump the environment.
<!-- factory:end -->
