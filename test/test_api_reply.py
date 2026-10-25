import unittest

from pydantic import ValidationError

from careconnect.api_reply import ApiReply

BASE = {"decision": "allow", "reply": "ok", "citations": []}


class ApiReplyTest(unittest.TestCase):
    def test_staged_defaults_to_false(self):
        self.assertIs(ApiReply(**BASE).staged, False)
        self.assertIs(ApiReply(**BASE).model_dump()["staged"], False)

    def test_staged_true_is_kept_and_must_be_a_bool(self):
        self.assertIs(ApiReply(**BASE, staged=True).staged, True)
        with self.assertRaises(ValidationError):
            ApiReply(**BASE, staged="yes")


if __name__ == "__main__":
    unittest.main()
