import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "AWS::EC2::NatGateway",
    "AWS::OpenSearchService::Domain",
    "AWS::Elasticsearch::Domain",
    "AWS::OpenSearchServerless::Collection",
}


class DataStackTemplateTest(unittest.TestCase):
    def setUp(self):
        # JSON is valid YAML; the template is written that way to avoid a YAML dependency.
        self.text = (ROOT / "infra/careconnect-data.yaml").read_text()
        self.template = json.loads(self.text)
        self.resources = self.template["Resources"]

    def of_type(self, type_):
        return [r for r in self.resources.values() if r["Type"] == type_]

    def test_every_taggable_resource_has_project_and_issue_tags(self):
        for name, res in self.resources.items():
            if res["Type"] == "AWS::S3::BucketPolicy":
                continue  # cannot take tags
            raw = res["Properties"].get("Tags")
            self.assertIsNotNone(raw, f"{name} has no Tags")
            tags = {t["Key"]: t["Value"] for t in raw}
            self.assertEqual(tags, {"Project": "careconnect", "issue": "93"}, name)

    def test_table_key_billing_and_ttl(self):
        (table,) = self.of_type("AWS::DynamoDB::Table")
        props = table["Properties"]
        self.assertEqual(props["TableName"], "careconnect-escalations")
        self.assertEqual(props["KeySchema"], [{"AttributeName": "ticket_id", "KeyType": "HASH"}])
        self.assertEqual(props["BillingMode"], "PAY_PER_REQUEST")
        self.assertEqual(
            props["TimeToLiveSpecification"], {"AttributeName": "expires_at", "Enabled": True}
        )

    def test_bucket_is_private(self):
        (bucket,) = self.of_type("AWS::S3::Bucket")
        block = bucket["Properties"]["PublicAccessBlockConfiguration"]
        self.assertEqual(set(block.values()), {True})
        self.assertEqual(len(block), 4)

    def test_state_machine_name_and_valid_definition(self):
        (sm,) = self.of_type("AWS::StepFunctions::StateMachine")
        self.assertEqual(sm["Properties"]["StateMachineName"], "careconnect-human-approval-workflow")
        definition = json.loads(sm["Properties"]["DefinitionString"])
        self.assertIn(definition["StartAt"], definition["States"])

    def test_outputs(self):
        self.assertEqual(
            set(self.template["Outputs"]),
            {"ApprovedDocsBucketName", "EscalationsTableName", "ApprovalWorkflowArn"},
        )

    def test_outputs_reference_their_resources(self):
        outputs = self.template["Outputs"]
        expected = {
            "ApprovedDocsBucketName": "AWS::S3::Bucket",
            "EscalationsTableName": "AWS::DynamoDB::Table",
            "ApprovalWorkflowArn": "AWS::StepFunctions::StateMachine",
        }
        for key, type_ in expected.items():
            ref = outputs[key]["Value"]["Ref"]
            self.assertEqual(self.resources[ref]["Type"], type_, key)

    def test_no_forbidden_resource_types(self):
        types = {r["Type"] for r in self.resources.values()}
        self.assertFalse(types & FORBIDDEN, types & FORBIDDEN)
        for res in self.resources.values():
            props = res.get("Properties", {})
            self.assertNotIn("ProvisionedConcurrencyConfig", props)
            self.assertNotIn("ProvisionedConcurrentExecutions", props)

    def test_no_account_ids_or_literal_arns(self):
        self.assertNotIn("arn:aws", self.text)
        self.assertIsNone(re.search(r"\b\d{12}\b", self.text))


class SyncApprovedDocsTest(unittest.TestCase):
    """Runs scripts/sync-approved-docs.sh with a fake `aws` that lists N objects."""

    def run_sync(self, remote_count):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "aws"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "$@" >> "{tmp}/calls"\n'
                f'if [ "$2" = "ls" ]; then for i in $(seq 1 {remote_count}); do echo obj$i; done; fi\n'
            )
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/sync-approved-docs.sh"), "test-bucket"],
                env=env, capture_output=True, text=True,
            )
            result.calls = (Path(tmp) / "calls").read_text().splitlines()
            return result

    def test_uploads_approved_folder_to_the_bucket(self):
        result = self.run_sync(self.local_count())
        src = ROOT / "Docs/Repo/careconnect-approved-docs/approved"
        syncs = [c.split() for c in result.calls if c.startswith("s3 sync ")]
        self.assertEqual(len(syncs), 1, result.calls)
        self.assertEqual(syncs[0][2:4], [str(src), "s3://test-bucket/approved/"])

    def local_count(self):
        src = ROOT / "Docs/Repo/careconnect-approved-docs/approved"
        return sum(1 for p in src.rglob("*") if p.is_file() and not p.name.startswith("."))

    def test_passes_when_counts_match(self):
        result = self.run_sync(self.local_count())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fails_when_counts_differ(self):
        result = self.run_sync(self.local_count() - 1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stderr)


if __name__ == "__main__":
    unittest.main()
