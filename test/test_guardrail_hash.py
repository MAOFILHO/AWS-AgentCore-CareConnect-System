import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/guardrail_hash.py"
TEMPLATE = ROOT / "infra/careconnect-bedrock.yaml"

spec = importlib.util.spec_from_file_location("guardrail_hash", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GuardrailHashTest(unittest.TestCase):
    def setUp(self):
        self.template = json.loads(TEMPLATE.read_text())
        self.base = module.guardrail_hash(self.template)

    def changed(self, edit):
        template = copy.deepcopy(self.template)
        edit(template["Resources"]["Guardrail"]["Properties"])
        return module.guardrail_hash(template)

    def test_hash_is_twelve_hex_chars(self):
        self.assertRegex(self.base, r"^[0-9a-f]{12}$")

    def test_changing_any_guardrail_property_changes_the_hash(self):
        for key in self.template["Resources"]["Guardrail"]["Properties"]:
            with self.subTest(key=key):
                self.assertNotEqual(self.changed(lambda p: p.__setitem__(key, "changed")), self.base)

    def test_adding_a_topic_changes_the_hash(self):
        topic = {"Name": "Prognosis", "Type": "DENY", "Definition": "Predicting how an illness will go."}
        add = lambda p: p["TopicPolicyConfig"]["TopicsConfig"].append(topic)
        self.assertNotEqual(self.changed(add), self.base)

    def test_other_resources_do_not_change_the_hash(self):
        template = copy.deepcopy(self.template)
        template["Resources"]["VectorIndex"]["Properties"]["Dimension"] = 512
        self.assertEqual(module.guardrail_hash(template), self.base)

    def test_cli_prints_the_hash_of_the_template(self):
        out = subprocess.run([sys.executable, str(SCRIPT), str(TEMPLATE)],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), self.base)


if __name__ == "__main__":
    unittest.main()
