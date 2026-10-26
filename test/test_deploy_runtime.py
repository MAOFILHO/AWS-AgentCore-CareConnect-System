import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/deploy-runtime.sh"
ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/careconnect_supervisor-abc123"
KB_ARN = "arn:aws:bedrock:us-east-1:000000000000:knowledge-base/KB12345678"
WORKFLOW_ARN = "arn:aws:states:us-east-1:000000000000:stateMachine:wf"
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/gw-123"
TABLE_ARN = "arn:aws:dynamodb:us-east-1:000000000000:table/careconnect-escalations"

# Fake aws: answers describe-stacks by stack name and output key; "empty" simulates a missing output.
FAKE_AWS = r"""#!/usr/bin/env bash
echo "aws $*" >> "$FAKE_LOG"
if [ "$1" = bedrock-agentcore-control ] && [ "$2" = list-agent-runtimes ]; then
  case "$*" in *"=='careconnectsupervisor'"*) echo "$FAKE_ARN" ;; *) echo "None" ;; esac
  exit 0
fi
if [ "$1" = bedrock-agentcore-control ] && [ "$2" = get-agent-runtime ]; then
  echo "arn:aws:iam::000000000000:role/service-role/RuntimeRole"
  exit 0
fi
if [ "$1" = iam ] && [ "$2" = put-role-policy ]; then
  while [ $# -gt 0 ]; do [ "$1" = --policy-document ] && echo "$2" > "$FAKE_POLICY"; shift; done
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
key=$(echo "$query" | sed -E "s/.*OutputKey=='([A-Za-z]+)'.*/\1/")
case "$stack/$key" in
  bedrock/KnowledgeBaseId) echo "KB12345678" ;;
  bedrock/GuardrailId) echo "gr-id" ;;
  bedrock/GuardrailVersion) echo "1" ;;
  data/EscalationsTableName) echo "careconnect-escalations" ;;
  data/ApprovalWorkflowArn) echo "arn:aws:states:us-east-1:000000000000:stateMachine:wf" ;;
  gateway/GatewayUrl) echo "$FAKE_GATEWAY_URL" ;;
  gateway/GatewayId) echo "$FAKE_GATEWAY_ID" ;;
  *) echo "None" ;;
esac
"""

# Fake agentcore: like the real toolkit, it fails unless the cwd holds the agent's config.
FAKE_AGENTCORE = r"""#!/usr/bin/env bash
if ! grep -q "careconnectsupervisor:" .bedrock_agentcore.yaml 2>/dev/null; then
  echo "Configuration not found: .bedrock_agentcore.yaml"; exit 1
fi
echo "agentcore $*" >> "$FAKE_LOG"
# The real console box wraps a long ARN over two lines.
echo "| Runtime ARN: ${FAKE_ARN:0:60} |"
echo "| ${FAKE_ARN:60} |"
"""


class DeployRuntimeTest(unittest.TestCase):
    def run_script(self, gateway_url="https://gw.example/mcp", arn=ARN, gateway_id="gw-123"):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            for name, body in (("aws", FAKE_AWS), ("agentcore", FAKE_AGENTCORE)):
                (bindir / name).write_text(body)
                (bindir / name).chmod(0o755)
            log = Path(tmp) / "log"
            policy = Path(tmp) / "policy.json"
            env = {
                **os.environ,
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "FAKE_LOG": str(log),
                "FAKE_GATEWAY_URL": gateway_url,
                "FAKE_GATEWAY_ID": gateway_id,
                "FAKE_ARN": arn,
                "FAKE_POLICY": str(policy),
            }
            proc = subprocess.run(
                ["bash", str(SCRIPT), "data", "bedrock", "gateway"],
                capture_output=True, text=True, env=env, cwd=tmp,
            )
            self.policy = json.loads(policy.read_text()) if policy.exists() else None
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
        self.assertIn(f"tag-resource --resource-arn {ARN} --region us-east-1 "
                      "--tags Project=careconnect,issue=152", log)

    def test_grants_the_runtime_role_retrieve_start_execution_invoke_gateway_and_put_escalation_tickets(self):
        proc, log = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--agent-runtime-id careconnect_supervisor-abc123", log)
        self.assertIn("iam put-role-policy --role-name RuntimeRole", log)
        self.assertIn("iam tag-role --role-name RuntimeRole "
                      "--tags Key=Project,Value=careconnect Key=issue,Value=156", log)
        grants = {s["Action"]: s["Resource"] for s in self.policy["Statement"]}
        self.assertEqual(grants, {
            "bedrock:Retrieve": KB_ARN,
            "states:StartExecution": WORKFLOW_ARN,
            "bedrock-agentcore:InvokeGateway": GATEWAY_ARN,
            "dynamodb:PutItem": TABLE_ARN,
        })

    def test_policy_has_no_wildcard_resource(self):
        self.run_script()
        for statement in self.policy["Statement"]:
            self.assertEqual(statement["Effect"], "Allow")
            self.assertNotIn("*", statement["Resource"])

    def test_no_listed_runtime_grants_nothing(self):
        proc, log = self.run_script(arn="None")
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("put-role-policy", log)

    def test_missing_gateway_id_fails_and_grants_nothing(self):
        proc, log = self.run_script(gateway_id="None")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("GATEWAY_ID", proc.stderr)
        self.assertNotIn("put-role-policy", log)

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

    def test_no_listed_runtime_fails_and_names_the_agent(self):
        proc, log = self.run_script(arn="None")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("careconnectsupervisor", proc.stderr)
        self.assertNotIn("tag-resource", log)


class AgentCoreConfigTest(unittest.TestCase):
    def test_config_names_the_supervisor_and_its_entrypoint(self):
        config = yaml.safe_load((ROOT / ".bedrock_agentcore.yaml").read_text())
        agent = config["agents"]["careconnectsupervisor"]
        self.assertEqual(config["default_agent"], "careconnectsupervisor")
        self.assertEqual(agent["name"], "careconnectsupervisor")
        self.assertEqual(agent["entrypoint"], "src/careconnect/runtime_entrypoint.py")
        self.assertTrue((ROOT / agent["entrypoint"]).is_file())
        self.assertEqual(agent["aws"]["network_configuration"]["network_mode"], "PUBLIC")

    def test_runtime_requirements_include_the_sdk(self):
        runtime = (ROOT / "src/requirements.txt").read_text().splitlines()
        self.assertTrue(any(line.startswith("bedrock-agentcore==") for line in runtime))
        self.assertTrue(any(line.startswith("mcp-proxy-for-aws==") for line in runtime))

    def test_entrypoint_imports_when_run_as_a_script_from_the_source_path(self):
        # The runtime runs the entrypoint as a script, so sys.path[0] is its own folder, not source_path.
        agent = yaml.safe_load((ROOT / ".bedrock_agentcore.yaml").read_text())["agents"]["careconnectsupervisor"]
        source = ROOT / agent["source_path"]
        script = (ROOT / agent["entrypoint"]).relative_to(source)
        code = f"import runpy, sys; sys.path[0] = {str(script.parent)!r}; runpy.run_path({str(script)!r})"
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run([sys.executable, "-c", code], cwd=source, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
