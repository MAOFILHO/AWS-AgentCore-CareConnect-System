import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/deploy-runtime.sh"
ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/careconnect_supervisor-abc123"

# Fake aws: answers describe-stacks by stack name and output key; "empty" simulates a missing output.
FAKE_AWS = r"""#!/usr/bin/env bash
echo "aws $*" >> "$FAKE_LOG"
stack=""; query=""
while [ $# -gt 0 ]; do
  case "$1" in
    --stack-name) stack="$2"; shift ;;
    --query) query="$2"; shift ;;
  esac
  shift
done
key=$(echo "$query" | sed -E "s/.*OutputKey=='([A-Za-z]+)'.*/\1/")
case "$stack/$key" in
  bedrock/KnowledgeBaseId) echo "KB12345678" ;;
  bedrock/GuardrailId) echo "gr-id" ;;
  bedrock/GuardrailVersion) echo "1" ;;
  data/ApprovalWorkflowArn) echo "arn:aws:states:us-east-1:000000000000:stateMachine:wf" ;;
  gateway/GatewayUrl) echo "$FAKE_GATEWAY_URL" ;;
  *) echo "None" ;;
esac
"""

FAKE_AGENTCORE = r"""#!/usr/bin/env bash
echo "agentcore $*" >> "$FAKE_LOG"
echo "Deployed: $FAKE_ARN"
"""


class DeployRuntimeTest(unittest.TestCase):
    def run_script(self, gateway_url="https://gw.example/mcp", arn=ARN):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            for name, body in (("aws", FAKE_AWS), ("agentcore", FAKE_AGENTCORE)):
                (bindir / name).write_text(body)
                (bindir / name).chmod(0o755)
            log = Path(tmp) / "log"
            env = {
                **os.environ,
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "FAKE_LOG": str(log),
                "FAKE_GATEWAY_URL": gateway_url,
                "FAKE_ARN": arn,
            }
            proc = subprocess.run(
                ["bash", str(SCRIPT), "data", "bedrock", "gateway"],
                capture_output=True, text=True, env=env,
            )
            return proc, log.read_text() if log.exists() else ""

    def test_deploys_with_the_five_values_and_prints_the_arn(self):
        proc, log = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip().splitlines()[-1], ARN)
        deploy = [l for l in log.splitlines() if l.startswith("agentcore deploy")]
        self.assertEqual(len(deploy), 1)
        for pair in (
            "CARECONNECT_KB_ID=KB12345678",
            "CARECONNECT_GATEWAY_URL=https://gw.example/mcp",
            "CARECONNECT_GUARDRAIL_ID=gr-id",
            "CARECONNECT_GUARDRAIL_VERSION=1",
            "CARECONNECT_STATE_MACHINE_ARN=arn:aws:states:us-east-1:000000000000:stateMachine:wf",
        ):
            self.assertIn(f"--env {pair}", deploy[0])
        self.assertIn("--region us-east-1", log)

    def test_empty_value_fails_and_does_not_deploy(self):
        proc, log = self.run_script(gateway_url="")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CARECONNECT_GATEWAY_URL", proc.stderr)
        self.assertNotIn("agentcore deploy", log)

    def test_missing_stack_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp)
            (bindir / "aws").write_text(FAKE_AWS)
            (bindir / "aws").chmod(0o755)
            env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
                   "FAKE_LOG": f"{tmp}/log", "FAKE_GATEWAY_URL": "x"}
            proc = subprocess.run(["bash", str(SCRIPT), "data", "bedrock", "nope"],
                                  capture_output=True, text=True, env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CARECONNECT_GATEWAY_URL", proc.stderr)

    def test_no_arn_in_deploy_output_fails(self):
        proc, _ = self.run_script(arn="no arn here")
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
