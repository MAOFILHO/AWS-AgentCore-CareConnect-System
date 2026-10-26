import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "scripts/deploy.sh"
TEARDOWN = ROOT / "scripts/teardown.sh"
APPROVED = ROOT / "Docs/Repo/careconnect-approved-docs/approved"
ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/careconnect_supervisor-abc123"
API_URL = "https://abc123.execute-api.us-east-1.amazonaws.com/careconnect"

# Fake aws: logs every call, answers stack outputs by stack and key, copies synced dirs for inspection.
FAKE_AWS = r"""#!/usr/bin/env bash
echo "aws $*" >> "$FAKE_LOG"
if [ "$1 $2" = "s3 ls" ]; then
  for i in $(seq 1 "$FAKE_DOC_COUNT"); do echo "doc $i"; done
  exit 0
fi
if [ "$1 $2" = "s3 sync" ]; then
  mkdir -p "$FAKE_SYNCED/$(basename "$3")"; cp -R "$3/." "$FAKE_SYNCED/$(basename "$3")/"
  exit 0
fi
stack=""; query=""
while [ $# -gt 0 ]; do
  case "$1" in
    --stack-name) stack="$2"; shift ;;
    --query) query="$2"; shift ;;
  esac
  shift
done
[ -z "$query" ] && exit 0
key=$(echo "$query" | sed -E "s/.*OutputKey=='([A-Za-z]+)'.*/\1/")
[ "$stack/$key" = "${FAKE_MISSING:-}" ] && { echo "None"; exit 0; }
case "$stack/$key" in
  careconnect-data/ApprovedDocsBucketName) echo "docs-bucket" ;;
  careconnect-data/ApprovalWorkflowArn) echo "arn:aws:states:us-east-1:000000000000:stateMachine:wf" ;;
  careconnect-bedrock/KnowledgeBaseId) echo "KB12345678" ;;
  careconnect-bedrock/DataSourceId) echo "DS12345678" ;;
  careconnect-bedrock/GuardrailId) echo "gr-id" ;;
  careconnect-bedrock/GuardrailVersion) echo "1" ;;
  careconnect-lambdas/ToolsFunctionArn) echo "arn:aws:lambda:us-east-1:000000000000:function:tools" ;;
  careconnect-gateway/GatewayUrl) echo "https://gw.example/mcp" ;;
  careconnect-api/ApiUrl) echo "$FAKE_API_URL" ;;
  careconnect-api/FrontendBucketName) echo "web-bucket" ;;
  careconnect-api/DistributionId) echo "DIST123" ;;
  careconnect-api/CloudFrontDomain) echo "d123.cloudfront.net" ;;
  *) echo "None" ;;
esac
"""

FAKE_AGENTCORE = r"""#!/usr/bin/env bash
echo "agentcore $* cwd=$PWD" >> "$FAKE_LOG"
echo "Deployed: $FAKE_ARN"
"""


class DeployTeardownTest(unittest.TestCase):
    def run_script(self, script, **extra_env):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            for name, body in (("aws", FAKE_AWS), ("agentcore", FAKE_AGENTCORE)):
                (bindir / name).write_text(body)
                (bindir / name).chmod(0o755)
            log, synced = Path(tmp) / "log", Path(tmp) / "synced"
            docs = len([p for p in APPROVED.rglob("*") if p.is_file() and not p.name.startswith(".")])
            env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_LOG": str(log),
                   "FAKE_SYNCED": str(synced), "FAKE_DOC_COUNT": str(docs), "FAKE_ARN": ARN,
                   "FAKE_API_URL": API_URL, **extra_env}
            proc = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, cwd=tmp)
            configs = {p.parent.name: p.read_text() for p in synced.rglob("config.js")}
            return proc, (log.read_text() if log.exists() else ""), configs

    def test_deploy_runs_the_stacks_in_order_and_ships_the_frontend(self):
        proc, log, configs = self.run_script(DEPLOY)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = log.splitlines()
        stacks = [re.search(r"--stack-name (\S+)", l).group(1) for l in lines
                  if l.startswith("aws cloudformation deploy")]
        self.assertEqual(stacks, ["careconnect-data", "careconnect-bedrock", "careconnect-lambdas",
                                  "careconnect-gateway", "careconnect-api"])
        for l in lines:
            if l.startswith("aws cloudformation deploy"):
                self.assertIn("--region us-east-1", l)
                self.assertIn("--tags Project=careconnect issue=125", l)
        api = next(l for l in lines if "--stack-name careconnect-api" in l and "deploy" in l)
        self.assertIn(f"AgentRuntimeArn={ARN}", api)
        idx = lambda text: next(i for i, l in enumerate(lines) if text in l)
        self.assertLess(idx("agentcore deploy"), idx("aws cloudformation deploy --stack-name careconnect-api"))
        self.assertLess(idx("aws cloudformation deploy --stack-name careconnect-api"), idx("s3://web-bucket/"))
        self.assertTrue(lines[idx("s3://web-bucket/")].startswith("aws s3 sync"))
        self.assertLess(idx("s3://web-bucket/"), idx("aws cloudfront create-invalidation"))
        self.assertIn("create-invalidation --distribution-id DIST123 --paths /*", log)
        self.assertLess(idx("aws s3 sync"), idx("start-ingestion-job"))
        self.assertIn("s3://docs-bucket/approved/", lines[idx("aws s3 sync")])
        self.assertIn("start-ingestion-job --knowledge-base-id KB12345678 --data-source-id DS12345678", log)
        self.assertIn(f'API_URL: "{API_URL}"', configs["frontend"])
        self.assertIn("YOUR-API-ID", (ROOT / "src/frontend/config.js").read_text())

    def test_allowed_origin_is_the_cloudfront_domain_of_the_api_stack(self):
        proc, log, _ = self.run_script(DEPLOY)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # The API stack derives ALLOWED_ORIGIN from its own distribution, so deploy passes no override.
        self.assertNotIn("allowed_origin", log.lower())
        self.assertNotIn("allowedorigin", log.lower())
        template = (ROOT / "infra/careconnect-api.yaml").read_text()
        self.assertIn('ALLOWED_ORIGIN: !Sub "https://${Distribution.DomainName}"', template)

    def test_a_missing_stack_output_stops_the_deploy(self):
        proc, log, _ = self.run_script(DEPLOY, FAKE_MISSING="careconnect-lambdas/ToolsFunctionArn")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("careconnect-lambdas has no output ToolsFunctionArn", proc.stderr)
        self.assertNotIn("--stack-name careconnect-gateway", log)

    def test_lambda_code_keys_change_with_the_source(self):
        proc, log, _ = self.run_script(DEPLOY)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name, param in (("careconnect-deterministic-safety", "SafetyCodeKey"),
                            ("careconnect-mock-hospital-tools", "ToolsCodeKey"),
                            ("careconnect-agentcore-proxy", "ProxyCodeKey")):
            src = ROOT / "Docs/Repo/lambda-functions" / name / "lambda_function.py"
            key = f"code/{name}-{hashlib.sha256(src.read_bytes()).hexdigest()[:12]}.zip"
            self.assertIn(f"{param}={key}", log)
            self.assertIn(f"s3://docs-bucket/{key}", log)

    def test_deploy_runs_agentcore_from_the_repo_root(self):
        proc, log, _ = self.run_script(DEPLOY)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"cwd={ROOT}", next(l for l in log.splitlines() if l.startswith("agentcore deploy")))

    def test_teardown_empties_the_buckets_and_deletes_in_reverse_order(self):
        proc, log, _ = self.run_script(TEARDOWN)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = log.splitlines()
        deleted = [re.search(r"--stack-name (\S+)", l).group(1) for l in lines
                   if l.startswith("aws cloudformation delete-stack")]
        self.assertEqual(deleted, ["careconnect-api", "careconnect-gateway", "careconnect-lambdas",
                                   "careconnect-bedrock", "careconnect-data"])
        idx = lambda text: next(i for i, l in enumerate(lines) if text in l)
        self.assertLess(idx("aws s3 rm s3://web-bucket"), idx("delete-stack --stack-name careconnect-api"))
        self.assertLess(idx("aws s3 rm s3://docs-bucket"), idx("delete-stack --stack-name careconnect-data"))
        for stack in deleted:
            self.assertLess(idx(f"delete-stack --stack-name {stack}"),
                            idx(f"stack-delete-complete --stack-name {stack}"))


if __name__ == "__main__":
    unittest.main()
