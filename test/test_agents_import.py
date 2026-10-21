import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from careconnect.supervisor_model import load_supervisor_model

AGENTS = [
    "careconnect.agents.document_processing_agent",
    "careconnect.agents.escalation_agent",
    "careconnect.agents.retrieval_agent",
    "careconnect.agents.supervisor_agent",
    "careconnect.agents.task_tool_agent",
    "careconnect.agents.verification_agent",
]
ROOT = Path(__file__).resolve().parent.parent


def _forbidden(name):
    def fail(*args, **kwargs):
        raise AssertionError(f"import created an AWS client or agent: {name}")
    return fail


def _fake_module(name, *attrs):
    module = mock.MagicMock(name=name)
    for attr in attrs:
        setattr(module, attr, _forbidden(f"{name}.{attr}"))
    return module


class AgentImportTest(unittest.TestCase):
    def import_clean(self, name):
        for loaded in [m for m in sys.modules if m.startswith("careconnect.agents")]:
            del sys.modules[loaded]
        boto3 = _fake_module("boto3", "client", "resource", "Session")
        strands = _fake_module("strands", "Agent")
        strands.tool = lambda fn: fn
        fakes = {
            "boto3": boto3,
            "strands": strands,
            "strands.tools": mock.MagicMock(),
            "strands.tools.mcp": mock.MagicMock(),
            "strands.tools.mcp.mcp_client": _fake_module("mcp_client", "MCPClient"),
            "mcp_proxy_for_aws": mock.MagicMock(),
            "mcp_proxy_for_aws.client": mock.MagicMock(),
        }
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.dict(sys.modules, fakes):
            return importlib.import_module(name)

    def test_every_agent_imports_without_settings_or_aws_clients(self):
        for name in AGENTS:
            with self.subTest(agent=name):
                self.import_clean(name)

    def test_supervisor_model_is_a_bedrock_model_id(self):
        self.assertRegex(load_supervisor_model(), r"^(us\.|global\.)?anthropic\.claude-")

    def test_old_agent_folder_holds_only_a_pointer(self):
        files = sorted(p.name for p in (ROOT / "Docs/Repo/agents").iterdir())
        self.assertEqual(files, ["README.md"])
        self.assertIn("src/careconnect/agents", (ROOT / "Docs/Repo/agents/README.md").read_text())

    def test_supervisor_model_comes_from_config(self):
        self.assertTrue(load_supervisor_model())
        with mock.patch("careconnect.supervisor_model.CONFIG_PATH", ROOT / "missing.json"):
            with self.assertRaises(FileNotFoundError):
                load_supervisor_model()

    def test_settings_are_read_at_call_time(self):
        mod = self.import_clean("careconnect.agents.retrieval_agent")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                mod.search_docs("parking")

    def test_verification_agent_gets_the_configured_model(self):
        verification = self.import_clean("careconnect.agents.verification_agent")
        agent_class = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"strands": mock.MagicMock(Agent=agent_class)}):
            verification.get_verification_agent()
        self.assertEqual(agent_class.call_args.kwargs["model"], load_supervisor_model())


if __name__ == "__main__":
    unittest.main()
