import contextlib
import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "start_ingestion.py"
REQUIREMENTS = SCRIPT.parent.parent / "requirements.txt"


class FakeCloudFormation:
    def __init__(self, outputs):
        self.outputs = outputs

    def describe_stacks(self, StackName):
        return {"Stacks": [{"Outputs": [
            {"OutputKey": k, "OutputValue": v} for k, v in self.outputs.items()
        ]}]}


class FakeBedrockAgent:
    def __init__(self):
        self.calls = []

    def start_ingestion_job(self, **kwargs):
        self.calls.append(kwargs)
        return {"ingestionJob": {"ingestionJobId": "JOB123"}}


def run_script(outputs):
    agent = FakeBedrockAgent()
    clients = {"cloudformation": FakeCloudFormation(outputs), "bedrock-agent": agent}
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda service, region_name=None: clients[service]
    saved = sys.modules.get("boto3")
    sys.modules["boto3"] = boto3
    try:
        spec = importlib.util.spec_from_file_location("start_ingestion", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            module.main("stack")
    finally:
        if saved is None:
            del sys.modules["boto3"]
        else:
            sys.modules["boto3"] = saved
    return agent, out.getvalue()


class StartIngestionTest(unittest.TestCase):
    def test_requirements_lists_boto3(self):
        names = [line.split("==")[0].strip() for line in REQUIREMENTS.read_text().splitlines()]
        self.assertIn("boto3", names)

    def test_starts_one_job_and_prints_its_id(self):
        agent, printed = run_script({"KnowledgeBaseId": "KB1", "DataSourceId": "DS1"})
        self.assertEqual(agent.calls, [{"knowledgeBaseId": "KB1", "dataSourceId": "DS1"}])
        self.assertEqual(printed.strip(), "JOB123")

    def test_empty_knowledge_base_id_exits_non_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            run_script({"KnowledgeBaseId": "", "DataSourceId": "DS1"})
        self.assertNotIn(ctx.exception.code, (0, None))

    def test_empty_data_source_id_exits_non_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            run_script({"KnowledgeBaseId": "KB1", "DataSourceId": ""})
        self.assertNotIn(ctx.exception.code, (0, None))


if __name__ == "__main__":
    unittest.main()
