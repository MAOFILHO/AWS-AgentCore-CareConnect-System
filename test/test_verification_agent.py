import io
import json
import os
import unittest
from unittest import mock

from careconnect.agents import verification_agent as agent
from careconnect.fakes import FakeGuardrail, FakeSafetyLambda


class VerificationInterfaceTest(unittest.TestCase):
    def test_fakes_and_adapters_satisfy_the_protocols(self):
        self.assertIsInstance(FakeSafetyLambda(), agent.SafetyLambda)
        self.assertIsInstance(agent.LambdaSafety(), agent.SafetyLambda)
        self.assertIsInstance(FakeGuardrail(), agent.Guardrail)
        self.assertIsInstance(agent.BedrockGuardrail(), agent.Guardrail)

    def test_checks_use_the_injected_fakes(self):
        self.assertEqual(
            agent.run_deterministic_safety("x", FakeSafetyLambda({"urgent": True})),
            {"classification": {"urgent": True}},
        )
        self.assertEqual(agent.run_guardrail("x", FakeGuardrail())["action"], "NONE")
        self.assertNotEqual(agent.run_guardrail("x", FakeGuardrail(allow=False))["action"], "NONE")

    def test_lambda_adapter_calls_invoke_with_the_expected_arguments(self):
        client = mock.Mock()
        client.invoke.return_value = {"Payload": io.BytesIO(b'{"classification": {}}')}
        self.assertEqual(agent.LambdaSafety(client).classify("hi"), {"classification": {}})
        client.invoke.assert_called_once_with(
            FunctionName="careconnect-deterministic-safety",
            InvocationType="RequestResponse",
            Payload=json.dumps({"text": "hi"}).encode("utf-8"),
        )

    def test_guardrail_adapter_calls_apply_guardrail_with_the_expected_arguments(self):
        client = mock.Mock()
        client.apply_guardrail.return_value = {"action": "NONE"}
        env = {"CARECONNECT_GUARDRAIL_ID": "gid", "CARECONNECT_GUARDRAIL_VERSION": "3"}
        with mock.patch.dict(os.environ, env):
            result = agent.BedrockGuardrail(client).apply("hi")
        self.assertEqual(result, {"action": "NONE", "reason": ""})
        client.apply_guardrail.assert_called_once_with(
            guardrailIdentifier="gid",
            guardrailVersion="3",
            source="OUTPUT",
            content=[{"text": {"text": "hi"}}],
            outputScope="FULL",
        )


if __name__ == "__main__":
    unittest.main()
