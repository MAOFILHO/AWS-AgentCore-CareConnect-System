import unittest
from pathlib import Path

import yaml

TEMPLATE = Path(__file__).resolve().parent.parent / "infra/careconnect-lambdas.yaml"
FUNCTIONS = {"careconnect-deterministic-safety", "careconnect-mock-hospital-tools"}


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


template = yaml.load(TEMPLATE.read_text(), Loader=_loader())
resources = template["Resources"]


def of_type(kind):
    return {k: v for k, v in resources.items() if v["Type"] == kind}


class LambdaTemplateTest(unittest.TestCase):
    def test_both_functions_run_python_312(self):
        functions = of_type("AWS::Lambda::Function")
        names = {f["Properties"]["FunctionName"] for f in functions.values()}
        self.assertEqual(names, FUNCTIONS)
        for f in functions.values():
            self.assertEqual(f["Properties"]["Runtime"], "python3.12")

    def test_every_resource_is_tagged(self):
        for name, res in resources.items():
            tags = {t["Key"]: t["Value"] for t in res.get("Properties", {}).get("Tags", [])}
            self.assertEqual(tags.get("Project"), "careconnect", name)
            self.assertEqual(tags.get("issue"), "94", name)

    def test_no_provisioned_concurrency(self):
        text = TEMPLATE.read_text().lower()
        self.assertNotIn("provisionedconcurrency", text)
        self.assertNotIn("reservedconcurrentexecutions", text)
        self.assertEqual(of_type("AWS::Lambda::Version"), {})
        self.assertEqual(of_type("AWS::Lambda::Alias"), {})

    def test_roles_have_no_wildcard_action(self):
        roles = of_type("AWS::IAM::Role")
        self.assertEqual(len(roles), 2)
        for name, role in roles.items():
            self.assertNotIn("ManagedPolicyArns", role["Properties"], name)
            for policy in role["Properties"]["Policies"]:
                for st in policy["PolicyDocument"]["Statement"]:
                    actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
                    for action in actions:
                        self.assertNotIn("*", action, name)
                    res = st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]]
                    for r in res:
                        self.assertNotEqual(r, "*", name)

    def test_description_fits_cloudformation_limit(self):
        self.assertLessEqual(len(template["Description"].encode()), 1024)

    def test_pydantic_layer_is_a_parameter(self):
        self.assertIn("PydanticLayerArn", template["Parameters"])

    def test_handlers_come_from_lambda_functions_dir(self):
        source = TEMPLATE.parent.parent / "Docs/Repo/lambda-functions"
        params = template["Parameters"]
        for f in of_type("AWS::Lambda::Function").values():
            props = f["Properties"]
            module, handler = props["Handler"].split(".")
            code = (source / props["FunctionName"] / f"{module}.py").read_text()
            self.assertIn(f"def {handler}(", code, props["FunctionName"])
            key = params[props["Code"]["S3Key"]["Ref"]]["Default"]
            self.assertEqual(key, props["FunctionName"] + ".zip")

    def test_each_role_writes_only_its_own_log_group(self):
        for f in of_type("AWS::Lambda::Function").values():
            props = f["Properties"]
            role = resources[props["Role"]["GetAtt"].split(".")[0]]
            for policy in role["Properties"]["Policies"]:
                for st in policy["PolicyDocument"]["Statement"]:
                    group = st["Resource"]["Sub"].split(".")[0].lstrip("${")
                    self.assertEqual(
                        resources[group]["Properties"]["LogGroupName"],
                        "/aws/lambda/" + props["FunctionName"],
                    )

    def test_outputs_are_both_function_arns(self):
        self.assertEqual(
            {o["Value"]["GetAtt"].split(".")[0] for o in template["Outputs"].values()},
            {"SafetyFunction", "ToolsFunction"},
        )


if __name__ == "__main__":
    unittest.main()
