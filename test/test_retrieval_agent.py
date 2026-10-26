import os
import sys
import unittest
from unittest import mock

from careconnect.fakes import FakeKnowledgeBase


def import_retrieval_agent():
    strands = mock.MagicMock(tool=lambda fn: fn)
    with mock.patch.dict(sys.modules, {"strands": strands}):
        sys.modules.pop("careconnect.agents.retrieval_agent", None)
        module = __import__("careconnect.agents.retrieval_agent", fromlist=["x"])
    sys.modules.pop("careconnect.agents.retrieval_agent", None)
    return module


agent = import_retrieval_agent()


class RetrievalInterfaceTest(unittest.TestCase):
    def test_fake_and_adapter_satisfy_the_protocol(self):
        self.assertIsInstance(FakeKnowledgeBase({}), agent.KnowledgeBase)
        self.assertIsInstance(agent.BedrockKnowledgeBase(), agent.KnowledgeBase)

    def test_agent_formats_passages_from_the_injected_fake(self):
        kb = FakeKnowledgeBase({"visiting-hours.md": "Visiting hours are 11:00-20:00."})
        out = agent.retrieve_passages("visiting", kb)
        self.assertIn("Passage 1\nVisiting hours are 11:00-20:00.", out)
        self.assertIn("Source:\nvisiting-hours.md", out)
        self.assertIn("No approved Riverside Health information", agent.retrieve_passages("zzz", kb))

    def test_adapter_calls_boto3_with_the_same_arguments(self):
        boto3 = mock.MagicMock()
        boto3.client.return_value.retrieve.return_value = {"retrievalResults": [{"score": 0.9}]}
        with mock.patch.dict(sys.modules, {"boto3": boto3}), \
                mock.patch.dict(os.environ, {"CARECONNECT_KB_ID": "kb-1"}):
            self.assertEqual(agent.BedrockKnowledgeBase().search("parking"), [{"score": 0.9}])
        boto3.client.assert_called_once_with("bedrock-agent-runtime", region_name="us-east-1")
        boto3.client.return_value.retrieve.assert_called_once_with(
            knowledgeBaseId="kb-1",
            retrievalQuery={"text": "parking"},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )


if __name__ == "__main__":
    unittest.main()
