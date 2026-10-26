import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra/careconnect-gateway.yaml"
FORBIDDEN = {"AWS::EC2::NatGateway", "AWS::OpenSearchService::Domain",
             "AWS::Elasticsearch::Domain"}
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

    def test_outputs_the_gateway_url_and_id(self):
        outputs = self.template["Outputs"]
        self.assertEqual(outputs["GatewayUrl"]["Value"], {"GetAtt": "Gateway.GatewayUrl"})
        self.assertEqual(
            outputs["GatewayId"]["Value"], {"GetAtt": "Gateway.GatewayIdentifier"}
        )

    def test_no_forbidden_resource_type(self):
        types = {r["Type"] for r in self.resources.values()}
        self.assertFalse(types & FORBIDDEN)
        self.assertNotIn("ProvisionedConcurrency", self.text)

    def test_no_account_ids_or_literal_arns(self):
        self.assertNotIn("arn:aws", self.text)
        self.assertIsNone(re.search(r"\b\d{12}\b", self.text))



if __name__ == "__main__":
    unittest.main()
