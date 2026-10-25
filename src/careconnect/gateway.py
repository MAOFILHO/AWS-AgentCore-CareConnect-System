"""Task/Tool seam: appointment status and staged refills behind a fake Gateway."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AppointmentStatus(BaseModel):
    patient_reference: str
    appointment_status: str
    department: str
    appointment_reference: str


class StagedRefillToolReply(BaseModel):
    """What the Gateway's stage_refill_request tool returns; every field is required."""
    model_config = ConfigDict(strict=True)
    action: Literal["submit_refill"]
    drug: str
    status: Literal["awaiting_approval"]
    idempotency_key: str
    submitted: Literal[False]


class StagedRefill(StagedRefillToolReply):
    patient_reference: str


class FakeGateway:
    """Synthetic hospital tools. A refill is staged for human approval, never submitted."""

    def check_appointment_status(self, patient_reference):
        return AppointmentStatus(
            patient_reference=patient_reference,
            appointment_status="scheduled",
            department="Gastroenterology",
            appointment_reference="APT-DEMO-1001",
        )

    def stage_refill_request(self, patient_reference, drug, idempotency_key=None):
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        return StagedRefill(
            patient_reference=patient_reference, drug=drug, idempotency_key=idempotency_key,
            action="submit_refill", status="awaiting_approval", submitted=False,
        )
