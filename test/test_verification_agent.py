import io
import json
import os
import unittest
from unittest import mock

from careconnect.agents import verification_agent as agent
from careconnect.fakes import FakeGuardrail, FakeSafetyLambda
from careconnect.safety_gate import classify


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


class GateSafety:
    """The deterministic safety Lambda: the same rules as the Safety gate."""

    def classify(self, text):
        return {"classification": classify(text)}


class PhoneNumberVerificationTest(unittest.TestCase):
    EVIDENCE = "Billing office: (555) 010-0160 - weekdays 09:00-17:00\nSource:\ns3://docs/approved/contact-directory.md"

    def verdict(self, request, answer, evidence=EVIDENCE):
        grounded = mock.Mock(structured_output=mock.Mock(grounded=True, unsupported_claims=[], reason="ok"))
        relevant = mock.Mock(structured_output=agent.RelevanceResult(relevant=True, reason="r"))
        model = mock.Mock(side_effect=[grounded, relevant])
        with mock.patch.object(agent, "get_verification_agent", return_value=model):
            return agent.verify(request, answer, evidence, GateSafety(), FakeGuardrail())["verification_status"]

    def test_an_approved_phone_number_passes_when_the_request_asks_for_a_phone_number(self):
        self.assertEqual(self.verdict("What is the phone number for billing?", self.EVIDENCE), "PASS")

    def test_an_approved_phone_number_fails_when_the_request_does_not_ask_for_one(self):
        self.assertEqual(self.verdict("billing office hours", self.EVIDENCE), "FAIL")

    def test_a_phone_number_missing_from_the_evidence_fails(self):
        answer = self.EVIDENCE.replace("0160", "0199")
        self.assertEqual(self.verdict("What is the phone number for billing?", answer), "FAIL")

    def test_other_personal_data_still_fails_beside_an_approved_phone_number(self):
        evidence = self.EVIDENCE + " jo@example.com"
        self.assertEqual(self.verdict("What is the phone number for billing?", evidence, evidence), "FAIL")


if __name__ == "__main__":
    unittest.main()
