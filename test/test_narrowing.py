import unittest
from pathlib import Path

from careconnect.narrowing import MAX_SENTENCES, answer_sentences

APPROVED = Path(__file__).resolve().parent.parent / "Docs/Repo/careconnect-approved-docs/approved"
FACILITIES = (APPROVED / "facilities-parking-wayfinding.md").read_text()
VISITING = (APPROVED / "visiting-hours-and-policy.md").read_text()


class AnswerSentencesTest(unittest.TestCase):
    def test_parking_question_keeps_the_parking_sentences_only(self):
        out = "\n".join(answer_sentences("Where can I park", FACILITIES))
        self.assertIn("multi-storey car park", out)
        self.assertNotIn("prayer", out)
        self.assertNotIn("Wi-Fi", out)

    def test_maternity_question_keeps_the_birth_partner_sentence(self):
        out = "\n".join(answer_sentences("What are the visiting rules for maternity?", VISITING))
        self.assertIn("birth partner", out)
        self.assertNotIn("ICU", out)

    def test_at_most_three_sentences_each_quoted_verbatim(self):
        sentences = answer_sentences("visiting hours", VISITING)
        self.assertLessEqual(len(sentences), MAX_SENTENCES)
        for sentence in sentences:
            self.assertIn(sentence, VISITING)

    def test_no_sentence_answers_the_request(self):
        self.assertEqual(answer_sentences("cafeteria menu prices", VISITING), [])

    def test_sentences_stay_in_document_order(self):
        text = "Parking is free. Bring a ticket. Parking bays are marked."
        self.assertEqual(answer_sentences("parking", text), ["Parking is free.", "Parking bays are marked."])

    def test_care_does_not_match_car(self):
        text = "Park in the car park. Child care is on level 2."
        self.assertEqual(answer_sentences("Where is child care", text), ["Child care is on level 2."])
