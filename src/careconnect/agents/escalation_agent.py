"""
CareConnect — Escalation Agent
==============================
Riverside Health patient-support assistant (console/CLI build).

WHAT THIS AGENT DOES
  When a patient asks something clinical, CareConnect must NOT answer — it must
  hand off to a human. This module records a durable ticket in DynamoDB and
  starts a Step Functions approval workflow so a clinician can take over.

HOW TO USE
  1. Set the Step Functions state machine ARN you created earlier:
         export CARECONNECT_STATE_MACHINE_ARN="<YOUR_STATE_MACHINE_ARN>"   # <-- UPDATE THIS
  2. Run it:
         PYTHONPATH=src python3 -m careconnect.agents.escalation_agent
  It creates a sample escalation ticket and starts the workflow.

WHERE YOU MIGHT NEED TO CHANGE THINGS
  - CARECONNECT_STATE_MACHINE_ARN: must be YOUR state machine ARN.
  - TABLE_NAME: change if you named the DynamoDB table differently.
  - region_name: change if you did not build in us-east-1.
"""

import uuid
import json
import os
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# AWS clients. UPDATE region_name if you did not build in us-east-1.
# ---------------------------------------------------------------------------
REGION = "us-east-1"

# UPDATE THIS if your DynamoDB table has a different name.
TABLE_NAME = "careconnect-escalations"

# UPDATE THIS by exporting CARECONNECT_STATE_MACHINE_ARN before running.
# It is read when the workflow starts, not when this file is imported.
def get_state_machine_arn():
    arn = os.environ.get("CARECONNECT_STATE_MACHINE_ARN")
    if not arn:
        raise ValueError("CARECONNECT_STATE_MACHINE_ARN is not configured.")
    return arn


# ---------------------------------------------------------------------------
# The two AWS calls this agent makes, as small interfaces. The boto3 adapters
# below are the defaults; tests use the fakes in careconnect.fakes.
# ---------------------------------------------------------------------------
@runtime_checkable
class TicketStore(Protocol):
    def create(self, ticket: dict) -> dict: ...


@runtime_checkable
class ApprovalWorkflow(Protocol):
    def start(self, ticket: dict) -> str: ...


class DynamoTicketStore:
    def create(self, ticket):
        import boto3

        boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME).put_item(Item=ticket)
        return ticket


class StepFunctionsWorkflow:
    def start(self, ticket):
        import boto3

        response = boto3.client("stepfunctions", region_name=REGION).start_execution(
            stateMachineArn=get_state_machine_arn(),
            input=json.dumps({"ticket_id": ticket["ticket_id"]}),
        )
        return response["executionArn"]


# ---------------------------------------------------------------------------
# The full escalation: save a ticket ('expires_at' is 30 days out, 2592000
# seconds, so tickets auto-clean via TTL), then start the approval workflow.
# Returns a patient-facing message plus the ticket ID and workflow execution.
# ---------------------------------------------------------------------------
def escalate(reason, category, request_details, store: TicketStore | None = None,
             workflow: ApprovalWorkflow | None = None):
    store = store or DynamoTicketStore()
    workflow = workflow or StepFunctionsWorkflow()
    ticket = store.create({
        "ticket_id": str(uuid.uuid4()),
        "category": category,
        "reason": reason,
        "request_details": request_details,
        "status": "pending_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + 2592000,
    })
    execution = workflow.start(ticket)
    return {
        "message": "Your request has been escalated to a human reviewer.",
        "ticket_id": ticket["ticket_id"],
        "workflow_execution": execution,
        "status": "pending_review",
    }


# ---------------------------------------------------------------------------
# Demo: escalate a sample clinical question and print the result.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    result = escalate(
        reason="Medication timing question requires clinician review.",
        category="clinical_question",
        request_details={
            "patient_request": "Should I stop my medication before my procedure?"
        },
    )
    print(json.dumps(result, indent=2))
