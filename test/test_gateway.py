import unittest

from careconnect.gateway import FakeGateway


class GatewayTest(unittest.TestCase):
    def test_refill_is_staged_not_submitted(self):
        out = FakeGateway().stage_refill_request("PAT-1", "Metformin", "key-1")
        self.assertEqual(out.status, "awaiting_approval")
        self.assertIs(out.submitted, False)
        self.assertEqual(out.idempotency_key, "key-1")

    def test_refill_without_idempotency_key_is_rejected(self):
        for key in (None, "", "   "):
            with self.assertRaises(ValueError):
                FakeGateway().stage_refill_request("PAT-1", "Metformin", key)

    def test_appointment_status_returns_synthetic_appointment(self):
        out = FakeGateway().check_appointment_status("PAT-1")
        self.assertEqual(out.appointment_reference, "APT-DEMO-1001")
        self.assertEqual(out.appointment_status, "scheduled")

    def test_patient_reference_has_no_default(self):
        with self.assertRaises(TypeError):
            FakeGateway().check_appointment_status()
        with self.assertRaises(TypeError):
            FakeGateway().stage_refill_request(drug="Metformin", idempotency_key="key-1")
        self.assertEqual(FakeGateway().check_appointment_status("PAT-9").patient_reference, "PAT-9")
