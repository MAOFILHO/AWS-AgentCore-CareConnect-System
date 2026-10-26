import unittest

from careconnect.fakes import (
    AnyHitKnowledgeBase,
    FakeApprovalWorkflow,
    FakeCostMeter,
    FakeEscalationTicketStore,
    FakeGrounding,
    FakeGuardrail,
    FakeKnowledgeBase,
    FakeRelevance,
)
from careconnect.supervisor import ESCALATION_NOTICE, UNVERIFIED_REASON, supervisor_flow
from careconnect.verification import verify

DOCS = {"visiting-hours-and-policy.md": "General ward visiting hours are 11:00-20:00."}


class VerificationGateTest(unittest.TestCase):
    def flow(self, documents=DOCS, grounding=None, guardrail=None, relevance=None, request="visiting hours",
             knowledge_base=FakeKnowledgeBase):
        return supervisor_flow(
            request,
            knowledge_base(documents),
            FakeEscalationTicketStore(),
            grounding=grounding or FakeGrounding(),
            guardrail=guardrail or FakeGuardrail(),
            relevance=relevance or FakeRelevance(), workflow=FakeApprovalWorkflow(), approved=set(documents),
            cost_meter=FakeCostMeter(),
        )

    def assert_notice_only(self, out):
        self.assertEqual(out["reply"], ESCALATION_NOTICE)
        self.assertEqual(out["citations"], [])
        self.assertEqual(out["decision"], "escalate")
        self.assertEqual(out["escalation"]["category"], "unverified_answer")
        self.assertEqual(out["escalation"]["reason"], UNVERIFIED_REASON)

    def test_draft_without_citation_shows_notice_only(self):
        result = verify("visiting", "Visiting is 11:00-20:00.", [], {}, FakeGrounding(), FakeGuardrail(), FakeRelevance())
        self.assertEqual(result.status, "FAIL")

    def test_citation_not_in_evidence_fails(self):
        result = verify("x", "x", ["other.md"], {"a.md": "x"}, FakeGrounding(), FakeGuardrail(), FakeRelevance())
        self.assertEqual(result.status, "FAIL")

    def test_ungrounded_claim_shows_notice_only(self):
        self.assert_notice_only(self.flow(grounding=FakeGrounding(grounded=False)))

    def test_phone_number_in_draft_shows_notice_only(self):
        self.assert_notice_only(self.flow({"a.md": "Visiting hours: call the ward on 555-123-4567."}))

    def test_mrn_in_draft_shows_notice_only(self):
        self.assert_notice_only(self.flow({"a.md": "Visiting hours for MRN-12345678."}))

    def test_guardrail_block_shows_notice_only(self):
        self.assert_notice_only(self.flow(guardrail=FakeGuardrail(allow=False)))

    def test_verification_error_shows_notice_only(self):
        self.assert_notice_only(self.flow(grounding=FakeGrounding(error=True)))

    def test_guardrail_error_shows_notice_only(self):
        self.assert_notice_only(self.flow(guardrail=FakeGuardrail(error=True)))

    def test_unrelated_evidence_shows_notice_only(self):
        self.assert_notice_only(self.flow(request="parking", knowledge_base=AnyHitKnowledgeBase))

    def test_relevance_error_shows_notice_only(self):
        self.assert_notice_only(self.flow(relevance=FakeRelevance(error=True)))

    def test_verify_fails_on_an_unrelated_draft(self):
        result = verify(
            "parking", "Visiting is 11:00-20:00.", ["a.md"], {"a.md": "Visiting is 11:00-20:00."},
            FakeGrounding(), FakeGuardrail(), FakeRelevance(),
        )
        self.assertEqual((result.status, result.reason), ("FAIL", "relevance"))

    def test_cited_grounded_draft_ships(self):
        out = self.flow()
        self.assertEqual(out["decision"], "allow")
        self.assertIn("11:00", out["reply"])
        self.assertEqual(out["citations"], ["visiting-hours-and-policy.md"])


if __name__ == "__main__":
    unittest.main()
