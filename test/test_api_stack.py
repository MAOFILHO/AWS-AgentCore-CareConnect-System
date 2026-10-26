import importlib.util
import os
import re
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "infra/careconnect-api.yaml"
PROXY = ROOT / "Docs/Repo/lambda-functions/careconnect-agentcore-proxy/lambda_function.py"
FORBIDDEN = {"AWS::EC2::NatGateway", "AWS::OpenSearchService::Domain",
             "AWS::Elasticsearch::Domain", "AWS::Lambda::Version", "AWS::Lambda::Alias"}
# Types CloudFormation cannot tag; the stack-level tags cover them.
UNTAGGABLE = {"AWS::Lambda::Permission", "AWS::S3::BucketPolicy",
              "AWS::CloudFront::OriginAccessControl", "AWS::ApiGatewayV2::Integration",
              "AWS::ApiGatewayV2::Route"}


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


class ApiStackTest(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text()
        self.template = yaml.load(self.text, Loader=_loader())
        self.resources = self.template["Resources"]

    def one(self, kind):
        (res,) = [r for r in self.resources.values() if r["Type"] == kind]
        return res["Properties"]

    def test_every_taggable_resource_is_tagged(self):
        for name, res in self.resources.items():
            if res["Type"] in UNTAGGABLE:
                continue
            tags = res["Properties"].get("Tags")
            if isinstance(tags, list):
                tags = {t["Key"]: t["Value"] for t in tags}
            self.assertEqual((tags or {}).get("Project"), "careconnect", name)
            self.assertEqual((tags or {}).get("issue"), "97", name)

    def test_no_forbidden_resource_type(self):
        for name, res in self.resources.items():
            self.assertNotIn(res["Type"], FORBIDDEN, name)
        lowered = self.text.lower()
        self.assertNotIn("provisionedconcurrency", lowered)
        self.assertNotIn("natgateway", lowered)
        self.assertNotIn("opensearch", lowered)

    def test_proxy_lambda_has_300_second_timeout(self):
        fn = self.one("AWS::Lambda::Function")
        self.assertEqual(fn["FunctionName"], "careconnect-agentcore-proxy")
        self.assertEqual(fn["Runtime"], "python3.12")
        self.assertEqual(fn["Timeout"], 300)
        self.assertEqual(fn["Environment"]["Variables"]["AGENT_RUNTIME_ARN"],
                         {"Ref": "AgentRuntimeArn"})

    def test_allowed_origin_is_the_cloudfront_domain(self):
        origin = self.one("AWS::Lambda::Function")["Environment"]["Variables"]["ALLOWED_ORIGIN"]
        self.assertEqual(origin, {"Sub": "https://${Distribution.DomainName}"})
        self.assertEqual(self.resources["Distribution"]["Type"], "AWS::CloudFront::Distribution")

    def test_invoke_policy_is_scoped_to_the_runtime_arn(self):
        role = self.one("AWS::IAM::Role")
        self.assertNotIn("ManagedPolicyArns", role)
        invoke = [st for p in role["Policies"] for st in p["PolicyDocument"]["Statement"]
                  if st["Action"] == "bedrock-agentcore:InvokeAgentRuntime"]
        self.assertEqual(len(invoke), 1)
        self.assertEqual(invoke[0]["Resource"],
                         [{"Ref": "AgentRuntimeArn"}, {"Sub": "${AgentRuntimeArn}/*"}])
        for p in role["Policies"]:
            for st in p["PolicyDocument"]["Statement"]:
                self.assertNotEqual(st["Resource"], "*")

    def test_api_routes_post_and_preflight_to_the_proxy(self):
        routes = {r["Properties"]["RouteKey"] for r in self.resources.values()
                  if r["Type"] == "AWS::ApiGatewayV2::Route"}
        self.assertEqual(routes, {"POST /careconnect", "OPTIONS /careconnect"})
        integration = self.one("AWS::ApiGatewayV2::Integration")
        # The proxy reads event["httpMethod"], which only payload format 1.0 carries.
        self.assertEqual(integration["PayloadFormatVersion"], "1.0")

    def test_bucket_is_private_behind_cloudfront_oac_with_cheapest_price_class(self):
        block = self.one("AWS::S3::Bucket")["PublicAccessBlockConfiguration"]
        self.assertEqual(set(block.values()), {True})
        self.assertEqual(len(block), 4)
        config = self.one("AWS::CloudFront::Distribution")["DistributionConfig"]
        self.assertEqual(config["PriceClass"], "PriceClass_100")
        (origin,) = config["Origins"]
        self.assertEqual(origin["OriginAccessControlId"], {"GetAtt": "OriginAccessControl.Id"})
        self.assertEqual(self.one("AWS::CloudFront::OriginAccessControl")
                         ["OriginAccessControlConfig"]["OriginAccessControlOriginType"], "s3")
        (st,) = self.one("AWS::S3::BucketPolicy")["PolicyDocument"]["Statement"]
        self.assertEqual(st["Principal"], {"Service": "cloudfront.amazonaws.com"})
        self.assertIn("AWS:SourceArn", st["Condition"]["StringEquals"])

    def test_outputs(self):
        self.assertEqual(set(self.template["Outputs"]),
                         {"ApiUrl", "CloudFrontDomain", "FrontendBucketName", "DistributionId"})

    def test_outputs_point_at_the_stack_resources(self):
        out = {k: v["Value"] for k, v in self.template["Outputs"].items()}
        self.assertEqual(out["CloudFrontDomain"], {"GetAtt": "Distribution.DomainName"})
        self.assertEqual(out["FrontendBucketName"], {"Ref": "FrontendBucket"})
        self.assertEqual(out["DistributionId"], {"Ref": "Distribution"})
        self.assertEqual(out["ApiUrl"], {"Sub": "https://${HttpApi}.execute-api.${AWS::Region}"
                                                ".amazonaws.com/careconnect"})
        for r in self.resources.values():
            if r["Type"] == "AWS::ApiGatewayV2::Route":
                self.assertEqual(r["Properties"]["Target"], {"Sub": "integrations/${ProxyIntegration}"})
        self.assertEqual(self.resources["ProxyIntegration"]["Properties"]["IntegrationUri"],
                         {"GetAtt": "ProxyFunction.Arn"})

    def test_no_account_ids_or_arns_in_template(self):
        self.assertIsNone(re.search(r"\d{12}", self.text))
        self.assertNotIn("arn:aws:bedrock-agentcore", self.text)

    def test_description_fits_cloudformation_limit(self):
        self.assertLessEqual(len(self.template["Description"].encode()), 1024)


class ProxyReadsStackEnvTest(unittest.TestCase):
    def test_proxy_takes_runtime_arn_and_origin_from_environment(self):
        env = {"AGENT_RUNTIME_ARN": "arn:test", "ALLOWED_ORIGIN": "https://d1.cloudfront.net"}
        with mock.patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location("proxy_env", PROXY)
            proxy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(proxy)
        self.assertEqual(proxy.AGENT_RUNTIME_ARN, "arn:test")
        self.assertEqual(proxy.ALLOWED_ORIGIN, "https://d1.cloudfront.net")


if __name__ == "__main__":
    unittest.main()
