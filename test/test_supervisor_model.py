import unittest

from careconnect.supervisor_model import load_supervisor_model


class SupervisorModelTest(unittest.TestCase):
    def test_default_is_a_model_the_account_can_call(self):
        self.assertEqual(
            load_supervisor_model(), "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )


if __name__ == "__main__":
    unittest.main()
