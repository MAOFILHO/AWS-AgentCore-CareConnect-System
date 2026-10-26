import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra/careconnect-gateway.yaml"
SCRIPT = ROOT / "scripts/deploy-runtime.sh"
TOOLS = {"check_appointment_status", "check_refill_eligibility", "stage_refill_request"}


def _loader():
    class Loader(yaml.SafeLoader):
        pass

    def tag(loader, suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return {suffix: loader.construct_scalar(node)}
        if isinstance(node, yaml.SequenceNode):
            return {suffix: loader.construct_sequence(node, deep=True)}
        return {suffix: loader.construct_mapping(node, deep=True)}

    Loader.add_multi_constructor("!", tag)
    return Loader


class GatewayTemplateTest(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text()
        self.template = yaml.load(self.text, Loader=_loader())
        self.resources = self.template["Resources"]

    def one(self, kind):
        (res,) = [r for r in self.resources.values() if r["Type"] == kind]
        return res["Properties"]

    def test_gateway_uses_iam_auth_over_mcp(self):
        gateway = self.one("AWS::BedrockAgentCore::Gateway")
        self.assertEqual(gateway["AuthorizerType"], "AWS_IAM")
        self.assertEqual(gateway["ProtocolType"], "MCP")

    def test_target_is_the_tools_lambda_with_its_three_tools(self):
        target = self.one("AWS::BedrockAgentCore::GatewayTarget")
        self.assertEqual(target["GatewayIdentifier"], {"Ref": "Gateway"})
        self.assertEqual(
            target["CredentialProviderConfigurations"],
            [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        lam = target["TargetConfiguration"]["Mcp"]["Lambda"]
        self.assertEqual(lam["LambdaArn"], {"Ref": "ToolsFunctionArn"})
        names = {t["Name"] for t in lam["ToolSchema"]["InlinePayload"]}
        self.assertEqual(names, TOOLS)
        code = (ROOT / "Docs/Repo/lambda-functions/careconnect-mock-hospital-tools"
                / "lambda_function.py").read_text()
        for name in TOOLS:
            self.assertIn(f'"{name}"', code)

    def test_gateway_role_may_only_invoke_the_tools_lambda(self):
        role = self.one("AWS::IAM::Role")
        self.assertNotIn("ManagedPolicyArns", role)
        (statement,) = role["AssumeRolePolicyDocument"]["Statement"]
        self.assertEqual(statement["Principal"], {"Service": "bedrock-agentcore.amazonaws.com"})
        (policy,) = role["Policies"]
        (st,) = policy["PolicyDocument"]["Statement"]
        self.assertEqual(st["Action"], "lambda:InvokeFunction")
        self.assertEqual(st["Resource"], {"Ref": "ToolsFunctionArn"})

    def test_every_taggable_resource_is_tagged(self):
        for name, res in self.resources.items():
            if res["Type"] == "AWS::BedrockAgentCore::GatewayTarget":
                continue  # takes no tags
            raw = res["Properties"]["Tags"]
            tags = raw if isinstance(raw, dict) else {t["Key"]: t["Value"] for t in raw}
            self.assertEqual(tags, {"Project": "careconnect", "issue": "96"}, name)

    def test_outputs_the_gateway_url(self):
        self.assertEqual(
            self.template["Outputs"]["GatewayUrl"]["Value"], {"GetAtt": "Gateway.GatewayUrl"}
        )

    def test_no_account_ids_or_literal_arns(self):
        self.assertNotIn("arn:aws", self.text)
        self.assertIsNone(re.search(r"\b\d{12}\b", self.text))


OUTPUTS = {
    "careconnect-data": {"ApprovalWorkflowArn": "sm-arn"},
    "careconnect-bedrock": {"KnowledgeBaseId": "kb-1", "GuardrailId": "gr-1",
                            "GuardrailVersion": "1"},
    "careconnect-gateway": {"GatewayUrl": "https://gw.example/mcp"},
}
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/careconnect-abc123"


class DeployRuntimeTest(unittest.TestCase):
    """Runs scripts/deploy-runtime.sh with a fake `aws` and a fake `agentcore` on PATH."""

    def run_deploy(self, outputs):
        with tempfile.TemporaryDirectory() as tmp:
            # The fake aws answers describe-stacks with FAKE_<stack>_<key>.
            aws = Path(tmp) / "aws"
            aws.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "aws $*" >> "{tmp}/calls"\n'
                'while [ $# -gt 0 ]; do case "$1" in\n'
                '  --stack-name) stack=${2//-/_}; shift;;\n'
                "  --query) key=${2#*OutputKey==\\'}; key=${key%%\\'*}; shift;;\n"
                "esac; shift; done\n"
                'v="FAKE_${stack}_${key}"; echo "${!v}"\n'
            )
            agentcore = Path(tmp) / "agentcore"
            agentcore.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "agentcore $*" >> "{tmp}/calls"\n'
                f'echo "Agent ARN: {RUNTIME_ARN}"\n'
            )
            aws.chmod(0o755)
            agentcore.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
            for stack, values in outputs.items():
                for key, value in values.items():
                    env[f"FAKE_{stack.replace('-', '_')}_{key}"] = value
            result = subprocess.run(
                ["bash", str(SCRIPT), "careconnect-data", "careconnect-bedrock",
                 "careconnect-gateway"],
                env=env, capture_output=True, text=True,
            )
            calls = Path(tmp) / "calls"
            result.calls = calls.read_text().splitlines() if calls.exists() else []
            return result

    def test_deploys_with_the_five_values_and_prints_the_runtime_arn(self):
        result = self.run_deploy(OUTPUTS)
        self.assertEqual(result.returncode, 0, result.stderr)
        (deploy,) = [c for c in result.calls if c.startswith("agentcore deploy")]
        self.assertEqual(
            re.findall(r"--env (\S+)", deploy),
            [
                "CARECONNECT_KB_ID=kb-1",
                "CARECONNECT_GATEWAY_URL=https://gw.example/mcp",
                "CARECONNECT_GUARDRAIL_ID=gr-1",
                "CARECONNECT_GUARDRAIL_VERSION=1",
                "CARECONNECT_STATE_MACHINE_ARN=sm-arn",
            ],
        )
        self.assertIn("Gateway URL: https://gw.example/mcp", result.stdout)
        self.assertIn(f"Runtime ARN: {RUNTIME_ARN}", result.stdout)

    def test_fails_before_deploy_when_a_value_is_empty(self):
        for stack, values in OUTPUTS.items():
            for key in values:
                with self.subTest(key=key):
                    outputs = {s: dict(v) for s, v in OUTPUTS.items()}
                    outputs[stack][key] = ""
                    result = self.run_deploy(outputs)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("is empty", result.stderr)
                    self.assertFalse([c for c in result.calls if c.startswith("agentcore")])

    def test_treats_none_as_empty(self):
        outputs = {s: dict(v) for s, v in OUTPUTS.items()}
        outputs["careconnect-bedrock"]["KnowledgeBaseId"] = "None"
        result = self.run_deploy(outputs)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CARECONNECT_KB_ID is empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
