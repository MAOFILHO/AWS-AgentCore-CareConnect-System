import importlib.util
import io
import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from careconnect.agents import verification_agent as agent
from careconnect.fakes import FakeGuardrail, FakeSafetyLambda
from careconnect.safety_gate import PII_PATTERNS

PHONE_PATTERN = PII_PATTERNS["phone"]
SAFETY_LAMBDA = (
    Path(__file__).resolve().parent.parent
    / "Docs/Repo/lambda-functions/careconnect-deterministic-safety/lambda_function.py"
)


class VerificationInterfaceTest(unittest.TestCase):
    def test_fakes_and_adapters_satisfy_the_protocols(self):
        self.assertIsInstance(FakeSafetyLambda(), agent.SafetyLambda)
        self.assertIsInstance(agent.LambdaSafety(), agent.SafetyLambda)
        self.assertIsInstance(FakeGuardrail(), agent.Guardrail)
        self.assertIsInstance(agent.BedrockGuardrail(), agent.Guardrail)

    def test_checks_use_the_injected_fakes(self):
        self.assertEqual(
            agent.run_deterministic_safety("x", FakeSafetyLambda({"urgent": True})),
            {"classification": {"clinical": False, "urgent": True, "injection": False, "pii": {}}},
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


class RelevanceCheckTest(unittest.TestCase):
    def reply(self, relevant):
        return mock.Mock(structured_output=agent.RelevanceResult(relevant=relevant, reason="r"))

    def check(self, reply):
        with mock.patch.object(agent, "get_verification_agent", return_value=mock.Mock(return_value=reply)):
            return agent.run_relevance_check("parking", "Visiting is 11:00-20:00.")

    def test_a_parsed_reply_is_the_result(self):
        self.assertTrue(self.check(self.reply(True)).relevant)
        self.assertFalse(self.check(self.reply(False)).relevant)

    def test_a_reply_that_is_not_a_relevance_result_is_not_relevant(self):
        for output in (None, "yes", {"relevant": True}):
            with self.subTest(output):
                self.assertFalse(self.check(mock.Mock(structured_output=output)).relevant)

    def test_verify_fails_when_the_draft_is_not_relevant(self):
        draft = "Visiting is 11:00-20:00.\nSource:\ns3://docs/approved/v.md"
        grounded = mock.Mock(structured_output=mock.Mock(grounded=True, unsupported_claims=[], reason="ok"))
        verdicts = {}
        for relevant in (True, False):
            model = mock.Mock(side_effect=[grounded, self.reply(relevant)])
            with mock.patch.object(agent, "get_verification_agent", return_value=model):
                verdicts[relevant] = agent.verify(
                    "visiting hours", draft, draft, FakeSafetyLambda(), FakeGuardrail()
                )["verification_status"]
        self.assertEqual(verdicts, {True: "PASS", False: "FAIL"})


class SafetyReplyFailsClosedTest(unittest.TestCase):
    DRAFT = "Visiting is 11:00-20:00.\nSource:\ns3://docs/approved/v.md"
    FULL = {"clinical": False, "urgent": False, "injection": False, "pii": {}}

    class Reply:
        def __init__(self, reply):
            self.reply = reply

        def classify(self, text):
            return self.reply

    def status(self, reply):
        grounded = mock.Mock(grounded=True, unsupported_claims=[], reason="ok")
        relevant = agent.RelevanceResult(relevant=True, reason="ok")
        with mock.patch.object(agent, "run_grounding_check", return_value=grounded), \
                mock.patch.object(agent, "run_relevance_check", return_value=relevant):
            return agent.verify("visiting hours", self.DRAFT, self.DRAFT, self.Reply(reply), FakeGuardrail())

    def test_an_error_payload_fails(self):
        self.assertEqual(self.status({"errorMessage": "boom"})["verification_status"], "FAIL")

    def test_a_reply_missing_any_flag_fails(self):
        for flag in self.FULL:
            with self.subTest(flag):
                partial = {k: v for k, v in self.FULL.items() if k != flag}
                self.assertEqual(self.status({"classification": partial})["verification_status"], "FAIL")

    def test_a_valid_reply_with_no_flags_passes(self):
        self.assertEqual(self.status({"classification": self.FULL})["verification_status"], "PASS")

    def test_a_draft_with_only_a_listed_number_passes_the_lambda_and_the_guardrail(self):
        for draft, expected in (
            ("Billing office: (555) 010-0160.\nSource:\ns3://docs/approved/v.md", "PASS"),
            ("Billing office: (555) 010-9999.\nSource:\ns3://docs/approved/v.md", "FAIL"),
            ("Billing: (555) 010-0160 or (555) 010-9999.\nSource:\ns3://docs/approved/v.md", "FAIL"),
        ):
            with self.subTest(draft):
                self.assertEqual(self.real_checks_status(draft), expected)

    def real_checks_status(self, draft):
        lambda_spec = importlib.util.spec_from_file_location("safety_lambda", SAFETY_LAMBDA)
        safety_lambda = importlib.util.module_from_spec(lambda_spec)
        lambda_spec.loader.exec_module(safety_lambda)

        class RealSafety:
            def classify(self, text):
                return {"classification": safety_lambda.classify(text)}

        client = mock.Mock()
        client.apply_guardrail.side_effect = lambda **kw: {
            "action": "GUARDRAIL_INTERVENED" if re.search(PHONE_PATTERN, kw["content"][0]["text"]["text"]) else "NONE"
        }
        env = {"CARECONNECT_GUARDRAIL_ID": "gid", "CARECONNECT_GUARDRAIL_VERSION": "3"}
        grounded = mock.Mock(grounded=True, unsupported_claims=[], reason="ok")
        relevant = agent.RelevanceResult(relevant=True, reason="ok")
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(agent, "run_grounding_check", return_value=grounded), \
                mock.patch.object(agent, "run_relevance_check", return_value=relevant):
            return agent.verify("billing phone", draft, draft, RealSafety(), agent.BedrockGuardrail(client))["verification_status"]

    def test_the_guardrail_adapter_sends_the_word_number_in_place_of_a_listed_number(self):
        client = mock.Mock()
        client.apply_guardrail.return_value = {"action": "NONE"}
        env = {"CARECONNECT_GUARDRAIL_ID": "gid", "CARECONNECT_GUARDRAIL_VERSION": "3"}
        with mock.patch.dict(os.environ, env):
            agent.BedrockGuardrail(client).apply("Billing: 555-010-0160. Other: 555-010-9999.")
        sent = client.apply_guardrail.call_args.kwargs["content"][0]["text"]["text"]
        self.assertEqual(sent, "Billing: number. Other: 555-010-9999.")

    def test_the_guardrail_adapter_sends_the_word_address_in_place_of_the_listed_address(self):
        client = mock.Mock()
        client.apply_guardrail.return_value = {"action": "NONE"}
        env = {"CARECONNECT_GUARDRAIL_ID": "gid", "CARECONNECT_GUARDRAIL_VERSION": "3"}
        with mock.patch.dict(os.environ, env):
            agent.BedrockGuardrail(client).apply("At 100 Riverside Drive, Riverside. Home: 12 Elm Street.")
        sent = client.apply_guardrail.call_args.kwargs["content"][0]["text"]["text"]
        self.assertEqual(sent, "At address. Home: 12 Elm Street.")

    def test_the_guardrail_adapter_leaves_the_source_file_name_out(self):
        client = mock.Mock()
        client.apply_guardrail.return_value = {"action": "NONE"}
        env = {"CARECONNECT_GUARDRAIL_ID": "gid", "CARECONNECT_GUARDRAIL_VERSION": "3"}
        draft = "Approved Riverside Health information:\nA fact.\nSource:\ns3://bucket/approved/emergency-and-urgent-care-info.md"
        with mock.patch.dict(os.environ, env):
            agent.BedrockGuardrail(client).apply(draft)
        sent = client.apply_guardrail.call_args.kwargs["content"][0]["text"]["text"]
        self.assertEqual(sent, "Approved Riverside Health information:\nA fact.")

    def test_the_adapter_returns_an_empty_reply_on_function_error_or_bad_json(self):
        for response in (
            {"FunctionError": "Unhandled", "Payload": io.BytesIO(b'{"errorMessage": "boom"}')},
            {"Payload": io.BytesIO(b"not json")},
        ):
            with self.subTest(response):
                client = mock.Mock()
                client.invoke.return_value = response
                self.assertEqual(agent.LambdaSafety(client).classify("hi"), {})


if __name__ == "__main__":
    unittest.main()
