import collections
import re
import unittest
from pathlib import Path

from careconnect.narrowing import MAX_SENTENCES, answer_sentences

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

    def test_flattened_contact_directory_still_quotes_the_pharmacy_phone_number(self):
        directory = flatten((APPROVED / "contact-directory.md").read_text())
        out = "\n".join(answer_sentences("What is the pharmacy phone number?", directory))
        self.assertRegex(out, r"\(555\) 010-\d{4}")

    def test_phone_question_quotes_the_department_line_not_the_generic_intro(self):
        directory = (APPROVED / "contact-directory.md").read_text()
        body = directory.split("\n", 1)[1]
        for text in (directory, body, flatten(directory), flatten(body)):
            for request, number in (
                ("What is the phone number for billing?", "(555) 010-0160"),
                ("What is the phone number for the pharmacy?", "(555) 010-0140"),
                ("What is the phone number for medical records?", "(555) 010-0180"),
            ):
                out = "\n".join(answer_sentences(request, text))
                self.assertIn(number, out, request)

    def test_statement_number_question_still_quotes_its_faq_line(self):
        billing = (APPROVED / "billing-faq.md").read_text()
        for text in (billing, flatten(billing)):
            out = "\n".join(answer_sentences("Which statement number do I give the billing office?", text))
            self.assertIn("contact the billing office with your statement number", out)

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
            for sentence in flat:
                self.assertIn(sentence, flatten(text), path.name)
            self.assertTrue(any(line in quoted for line in lines for quoted in flat), path.name)

    def test_records_request_duration_does_not_quote_the_fees_section(self):
        records = (APPROVED / "medical-records-request.md").read_text()
        for text in (records, flatten(records)):
            out = "\n".join(answer_sentences("How long does a records request take?", text))
            self.assertNotIn("fee", out.lower())

    def test_flattened_reply_holds_no_markdown_marker_and_no_document_title(self):
        for path in sorted(APPROVED.glob("*.md")):
            text = path.read_text()
            title = text.splitlines()[0].lstrip("# ")
            for heading in (line for line in text.splitlines() if line.startswith("## ")):
                for sentence in answer_sentences(heading.lstrip("# "), flatten(text)):
                    self.assertNotIn("#", sentence, path.name)
                    self.assertNotIn(title, sentence, path.name)

    def test_flattened_general_ward_question_quotes_the_general_ward_section_only(self):
        out = answer_sentences("What are the general ward visiting hours?", flatten(VISITING))
        self.assertTrue(out)
        self.assertIn("11:00", out[0])
        self.assertNotIn("Other visitors follow general ward hours.", out)
        for sentence in out:
            self.assertIn(sentence, flatten(VISITING.split("## Intensive")[0]))

    def test_flattened_reply_lies_in_one_section_of_the_document(self):
        for path in sorted(APPROVED.glob("*.md")):
            text = path.read_text()
            sections = [flatten(s) for s in re.split(r"(?m)^(?=## )", text)[1:]]
            for heading in (line for line in text.splitlines() if line.startswith("## ")):
                out = answer_sentences(heading.lstrip("# "), flatten(text))
                if out:
                    self.assertTrue(any(all(s in section for s in out) for section in sections), (path.name, out))

    def test_flattened_intro_sentence_under_the_title_is_quotable(self):
        intros = 0
        for path in sorted(APPROVED.glob("*.md")):
            text = path.read_text()
            intro = re.split(r"(?m)^## ", text)[0].split("\n", 1)[1]
            counts = collections.Counter(re.findall(r"[a-z0-9]+", text.lower()))
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", flatten(intro)):
                if sentence:
                    intros += 1
                    words = sorted(set(re.findall(r"[a-z0-9]+", sentence.lower())), key=lambda w: (counts[w], w))
                    question = " ".join(words[:3])
                    self.assertIn(sentence, answer_sentences(question, flatten(text)), (path.name, question))
        self.assertEqual(intros, 19)
