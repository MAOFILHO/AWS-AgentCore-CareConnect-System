import unittest

from careconnect.fakes import FakeEscalationTicketStore, FakeKnowledgeBase
from careconnect.supervisor import supervisor_flow

GOLDEN_SCENARIOS = [
    {
        "name": "unclear dizzy request fails closed",
        "request": "my mum feels dizzy, can she still have her appointment?",
        "decision": "escalate",
    },
]


class GoldenScenarioTest(unittest.TestCase):
    def test_all_golden_scenarios_pass(self):
        for scenario in GOLDEN_SCENARIOS:
            with self.subTest(scenario["name"]):
                kb = FakeKnowledgeBase(
                    {"visiting-hours-and-policy.md": "General ward visiting hours are 11:00-20:00."}
                )
                tickets = FakeEscalationTicketStore()
                out = supervisor_flow(scenario["request"], kb, tickets)
                self.assertEqual(out["decision"], scenario["decision"])
                self.assertEqual(len(tickets.tickets), 1)
