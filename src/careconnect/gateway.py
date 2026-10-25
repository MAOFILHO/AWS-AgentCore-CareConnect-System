"""Task/Tool seam: appointment status and staged refills behind a fake Gateway."""

from typing import Literal

from pydantic import BaseModel


class AppointmentStatus(BaseModel):
    patient_reference: str
    appointment_status: str
    department: str
    appointment_reference: str


class StagedRefillResult(BaseModel):
    """What the Gateway's stage_refill_request tool returns."""
    action: Literal["submit_refill"] = "submit_refill"
    drug: str
    status: Literal["awaiting_approval"] = "awaiting_approval"
    idempotency_key: str
    submitted: Literal[False] = False


class StagedRefill(StagedRefillResult):
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
        return StagedRefill(patient_reference=patient_reference, drug=drug, idempotency_key=idempotency_key)
