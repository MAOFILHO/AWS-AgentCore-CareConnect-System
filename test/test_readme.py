import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()


class ReadmeTest(unittest.TestCase):
    def test_has_sections_with_commands(self):
        for heading in ("## Run and test", "## Deploy", "## Teardown"):
            self.assertIn(heading, README)
        self.assertIn("scripts/deploy.sh", README)
        self.assertIn("scripts/teardown.sh", README)
        self.assertIn("npm test", README)

    def test_referenced_paths_exist(self):
        paths = set(re.findall(r"`((?:scripts|src|test|Docs|infra)/[\w./-]+|[A-Z]+\.md)`", README))
        self.assertTrue(paths)
        for p in paths:
            self.assertTrue((ROOT / p).exists(), p)

    def test_no_account_id_arn_or_key(self):
        self.assertIsNone(re.search(r"\b\d{12}\b", README))
        self.assertNotIn("arn:aws", README)
        self.assertIsNone(re.search(r"AKIA[0-9A-Z]{16}", README))


if __name__ == "__main__":
    unittest.main()
