# AWS-AgentCore-CareConnect-System

Built with a software factory. See AGENTS.md.

See `GLOSSARY.md` for the terms. Stay on the AWS Free Tier or the lowest-cost option, and never add a NAT Gateway.

## Run and test
```bash
npm ci || npm install
python3 -m pip install -r requirements.txt
npm test
PYTHONPATH=src python3 -m unittest discover -s test
npm run typecheck --if-present
npm run lint --if-present
npm run build --if-present
```
The chat page is `src/frontend/index.html`; set the API URL in `src/frontend/config.js`.

## Deploy
```bash
scripts/deploy.sh
```
Needs the AWS CLI signed in to the target account. Re-runs update in place.

## Teardown
```bash
scripts/teardown.sh
```
Run `agentcore destroy` too: the AgentCore runtime is not a stack.
