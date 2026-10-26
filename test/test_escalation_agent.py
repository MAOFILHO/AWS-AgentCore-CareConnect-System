import json
import os
import sys
import unittest
from unittest import mock

from careconnect.agents import escalation_agent as agent
from careconnect.fakes import FakeApprovalWorkflow, FakeEscalationTicketStore


class EscalationInterfaceTest(unittest.TestCase):
    def test_fakes_and_adapters_satisfy_the_protocols(self):
        self.assertIsInstance(FakeEscalationTicketStore(), agent.TicketStore)
        self.assertIsInstance(agent.DynamoTicketStore(), agent.TicketStore)
        self.assertIsInstance(FakeApprovalWorkflow(), agent.ApprovalWorkflow)
        self.assertIsInstance(agent.StepFunctionsWorkflow(), agent.ApprovalWorkflow)

    def test_escalate_uses_the_injected_fakes(self):
        store, workflow = FakeEscalationTicketStore(), FakeApprovalWorkflow()
        out = agent.escalate("why", "clinical_question", {"q": 1}, store=store, workflow=workflow)
        ticket = store.tickets[0]
        self.assertEqual(workflow.started, [ticket])
        self.assertEqual(
            (out["ticket_id"], out["status"], out["workflow_execution"]),
            (ticket["ticket_id"], "pending_review", "fake-execution"),
        )
        self.assertEqual((ticket["category"], ticket["reason"]), ("clinical_question", "why"))

    def test_adapters_call_boto3_with_the_same_arguments(self):
        boto3 = mock.MagicMock()
        boto3.client.return_value.start_execution.return_value = {"executionArn": "arn:exec"}
        ticket = {"ticket_id": "T1", "status": "pending_review"}
        env = {"CARECONNECT_STATE_MACHINE_ARN": "arn:sm"}
        with mock.patch.dict(sys.modules, {"boto3": boto3}), mock.patch.dict(os.environ, env):
            self.assertEqual(agent.DynamoTicketStore().create(ticket), ticket)
            self.assertEqual(agent.StepFunctionsWorkflow().start(ticket), "arn:exec")
        boto3.resource.assert_called_once_with("dynamodb", region_name="us-east-1")
        boto3.resource.return_value.Table.assert_called_once_with("careconnect-escalations")
        boto3.resource.return_value.Table.return_value.put_item.assert_called_once_with(Item=ticket)
        boto3.client.assert_called_once_with("stepfunctions", region_name="us-east-1")
        boto3.client.return_value.start_execution.assert_called_once_with(
            stateMachineArn="arn:sm", input=json.dumps({"ticket_id": "T1"})
        )


if __name__ == "__main__":
    unittest.main()
