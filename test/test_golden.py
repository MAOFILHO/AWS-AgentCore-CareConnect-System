import unittest
from pathlib import Path

from careconnect.fakes import (
    FakeEscalationTicketStore,
    FakeGrounding,
    FakeGuardrail,
    FakeKnowledgeBase,
)
from careconnect.supervisor import supervisor_flow

GOLDEN_SCENARIOS = [
    {
        "name": "unclear dizzy request fails closed",
        "request": "my mum feels dizzy, can she still have her appointment?",
        "decision": "escalate",
    },
    {
        "name": "mum feels dizzy fails closed",
        "request": "my mum feels dizzy",
        "decision": "escalate",
    },
    {
        "name": "fever and rash fails closed",
        "request": "I have a fever and rash",
        "decision": "escalate",
    },
    {
        "name": "lightheaded request fails closed",
        "request": "my dad is lightheaded, can he come to his appointment?",
        "decision": "escalate",
    },
    {
        "name": "chest and cough request fails closed",
        "request": "I have a cough and my chest hurts",
        "decision": "escalate",
    },
    {
        "name": "headache request fails closed",
        "request": "I get a headache after my new tablets",
        "decision": "escalate",
    },
]

APPROVED = Path(__file__).resolve().parent.parent / "Docs/Repo/careconnect-approved-docs/approved"


class GoldenScenarioTest(unittest.TestCase):
    def test_all_golden_scenarios_pass(self):
        for scenario in GOLDEN_SCENARIOS:
            with self.subTest(scenario["name"]):
                kb = FakeKnowledgeBase({p.name: p.read_text() for p in APPROVED.glob("*.md")})
                tickets = FakeEscalationTicketStore()
                out = supervisor_flow(
                    scenario["request"], kb, tickets, FakeGrounding(), FakeGuardrail()
                )
                self.assertEqual(out["decision"], scenario["decision"])
                self.assertEqual(len(tickets.tickets), 1 if scenario["decision"] == "escalate" else 0)
