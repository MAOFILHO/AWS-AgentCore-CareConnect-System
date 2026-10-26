import unittest
from pathlib import Path

from careconnect.narrowing import MAX_SENTENCES, _sentences, answer_sentences

APPROVED = Path(__file__).resolve().parent.parent / "Docs/Repo/careconnect-approved-docs/approved"
FACILITIES = (APPROVED / "facilities-parking-wayfinding.md").read_text()
VISITING = (APPROVED / "visiting-hours-and-policy.md").read_text()


def flatten(text):
    return " ".join(text.split())


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

    def test_flattened_parking_passage_keeps_the_parking_sentences_only(self):
        out = "\n".join(answer_sentences("Where can I park?", flatten(FACILITIES)))
        self.assertIn("multi-storey car park", out)
        self.assertNotIn("prayer", out)

    def test_flattened_visiting_passage_keeps_the_birth_partner_sentence(self):
        out = "\n".join(answer_sentences("What time can my husband visit me in maternity?", flatten(VISITING)))
        self.assertIn("birth partner", out)
        self.assertNotIn("ICU", out)

    def test_every_flattened_approved_document_keeps_all_the_text_of_the_original(self):
        for path in sorted(APPROVED.glob("*.md")):
            text = path.read_text()
            flat = flatten(text)
            quoted = [sentence for _, sentence in _sentences(flat)]
            for sentence in quoted:
                self.assertIn(sentence, flat, path.name)
            joined = " ".join(quoted)
            for _, sentence in _sentences(text):
                self.assertIn(sentence, joined, path.name)

    def test_flattened_contact_directory_still_quotes_the_pharmacy_phone_number(self):
        directory = flatten((APPROVED / "contact-directory.md").read_text())
        out = "\n".join(answer_sentences("What is the pharmacy phone number?", directory))
        self.assertRegex(out, r"\(555\) 010-\d{4}")

    def test_flattened_billing_question_quotes_the_billing_timing_sentence(self):
        billing = (APPROVED / "billing-faq.md").read_text()
        out = "\n".join(answer_sentences("When will I get my bill?", flatten(billing)))
        self.assertIn("within 14 days", out)

    def test_flattened_heading_question_quotes_a_sentence_of_the_line_break_reply(self):
        for path in sorted(APPROVED.glob("*.md")):
            text = path.read_text()
            heading = next(line for line in text.splitlines() if line.startswith("## "))
            request = heading.lstrip("# ")
            flat = answer_sentences(request, flatten(text))
            lines = answer_sentences(request, text)
            self.assertTrue(any(line in quoted for line in lines for quoted in flat), path.name)
