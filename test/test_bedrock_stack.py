import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "AWS::EC2::NatGateway",
    "AWS::OpenSearchService::Domain",
    "AWS::Elasticsearch::Domain",
    "AWS::OpenSearchServerless::Collection",
}
NO_TAGS = {"AWS::Bedrock::DataSource", "AWS::Bedrock::GuardrailVersion"}


class BedrockStackTemplateTest(unittest.TestCase):
    def setUp(self):
        # JSON is valid YAML; written that way to avoid a YAML dependency.
        self.text = (ROOT / "infra/careconnect-bedrock.yaml").read_text()
        self.template = json.loads(self.text)
        self.resources = self.template["Resources"]

    def of_type(self, type_):
        return [r for r in self.resources.values() if r["Type"] == type_]

    def test_guardrail_denies_the_four_clinical_topics(self):
        (g,) = self.of_type("AWS::Bedrock::Guardrail")
        topics = g["Properties"]["TopicPolicyConfig"]["TopicsConfig"]
        self.assertEqual(
            {t["Name"] for t in topics}, {"Diagnosis", "Dosage", "Treatment", "Triage"}
        )
        self.assertEqual({t["Type"] for t in topics}, {"DENY"})

    def test_guardrail_masks_pii_and_has_a_valid_mrn_regex(self):
        (g,) = self.of_type("AWS::Bedrock::Guardrail")
        info = g["Properties"]["SensitiveInformationPolicyConfig"]
        self.assertTrue(info["PiiEntitiesConfig"])
        self.assertEqual({e["Action"] for e in info["PiiEntitiesConfig"]}, {"ANONYMIZE"})
        (mrn,) = [r for r in info["RegexesConfig"] if "MRN" in r["Name"]]
        self.assertEqual(mrn["Action"], "ANONYMIZE")
        pattern = re.compile(mrn["Pattern"])
        self.assertTrue(pattern.search("my MRN 12345678 is"))
        self.assertFalse(pattern.search("no record number here"))

    def test_guardrail_has_a_published_version(self):
        (v,) = self.of_type("AWS::Bedrock::GuardrailVersion")
        ident = v["Properties"]["GuardrailIdentifier"]
        self.assertEqual(self.resources[ident["Fn::GetAtt"][0]]["Type"], "AWS::Bedrock::Guardrail")

    def test_vector_store_is_s3_vectors_not_opensearch(self):
        (kb,) = self.of_type("AWS::Bedrock::KnowledgeBase")
        storage = kb["Properties"]["StorageConfiguration"]
        self.assertEqual(storage["Type"], "S3_VECTORS")
        self.assertIn("S3VectorsConfiguration", storage)
        self.assertNotIn("OpensearchServerlessConfiguration", storage)
        self.assertEqual(len(self.of_type("AWS::S3Vectors::VectorBucket")), 1)
        self.assertEqual(len(self.of_type("AWS::S3Vectors::Index")), 1)

    def test_knowledge_base_uses_titan_embeddings_matching_the_index(self):
        (kb,) = self.of_type("AWS::Bedrock::KnowledgeBase")
        arn = json.dumps(kb["Properties"]["KnowledgeBaseConfiguration"])
        self.assertIn("amazon.titan-embed-text-v2:0", arn)
        (index,) = self.of_type("AWS::S3Vectors::Index")
        self.assertEqual(index["Properties"]["Dimension"], 1024)

    def test_data_source_reads_the_approved_prefix(self):
        (ds,) = self.of_type("AWS::Bedrock::DataSource")
        cfg = ds["Properties"]["DataSourceConfiguration"]
        self.assertEqual(cfg["Type"], "S3")
        self.assertEqual(cfg["S3Configuration"]["InclusionPrefixes"], ["approved/"])

    def test_outputs(self):
        self.assertTrue(
            {"KnowledgeBaseId", "GuardrailId", "GuardrailVersion", "DataSourceId"}
            <= set(self.template["Outputs"])
        )

    def test_every_taggable_resource_has_project_and_issue_tags(self):
        for name, res in self.resources.items():
            if res["Type"] in NO_TAGS:
                continue
            raw = res["Properties"].get("Tags")
            self.assertIsNotNone(raw, f"{name} has no Tags")
            if isinstance(raw, dict):  # the Bedrock knowledge base takes a map
                tags = raw
            else:
                tags = {t["Key"]: t["Value"] for t in raw}
            self.assertEqual(tags, {"Project": "careconnect", "issue": "95"}, name)

    def test_no_forbidden_resource_types(self):
        types = {r["Type"] for r in self.resources.values()}
        self.assertFalse(types & FORBIDDEN, types & FORBIDDEN)

    def test_no_account_ids_or_literal_arns(self):
        self.assertNotIn("arn:aws", self.text)
        self.assertIsNone(re.search(r"\b\d{12}\b", self.text))


if __name__ == "__main__":
    unittest.main()
