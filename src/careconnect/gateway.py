"""Task/Tool seam: appointment status and staged refills behind a fake Gateway."""

from typing import Literal

from pydantic import BaseModel


class AppointmentStatus(BaseModel):
    patient_reference: str
    appointment_status: str
    department: str
    appointment_reference: str


class StagedRefill(BaseModel):
    action: Literal["submit_refill"] = "submit_refill"
    drug: str
    status: Literal["awaiting_approval"] = "awaiting_approval"
    idempotency_key: str
    submitted: Literal[False] = False


class FakeGateway:
    """Synthetic hospital tools. A refill is staged for human approval, never submitted."""

    def check_appointment_status(self, patient_reference="PATIENT-DEMO-001"):
        return AppointmentStatus(
            patient_reference=patient_reference,
            appointment_status="scheduled",
            department="Gastroenterology",
            appointment_reference="APT-DEMO-1001",
        )

    def stage_refill_request(self, drug, idempotency_key=None):
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        return StagedRefill(drug=drug, idempotency_key=idempotency_key)
