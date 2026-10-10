"""Brief parsing (I12): mail records, the technical release and the reference come from the run's brief, never from code.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from agents.common import mail_records, mentions, reference, technical_records  # noqa: E402
from agents.webmail.agent import wanted  # noqa: E402

PUBLIC_BRIEF = (ROOT / "eval/public-1/run-brief.md").read_text()

# Another scenario's wording: other subjects, senders, domain and sentence shapes, the same kinds of rules.
SYNTHETIC = """# Prepare a tender response

You work for Example Pumps AG. Prepare one bid for Town of Sample: pumps (TX-0001-0042). The scenario date is 2030-05-01.

## Rules

5. Discount: take the latest message by the managing board (board@ at the bidder's domain) approving a discount for
this exact reference. Other senders do not apply.

## Additional rules

- Clauses: resolve a clause key in the newest Rabattmatrix message from pricing@ plus the bidder mailbox domain.
- Stroke derivation: for a usable stroke, add twice the end reserve given in the revision-specific Hubfreigabe.
- Authority: authorized subjects and senders are Hubfreigabe/engineering; Kartonsatz/shipping; Kursblatt/treasury.
- Contacts: questions go to desk@example-pumps.test.
- Mail search combines words with AND: use the tender reference plus a subject/topic. Read the inbox/archive results.

## Site access

- one: https://one.test
  Username: `user` · Password: `secret@word`
"""


def pairs(found):
    return {(r["subject"], r["sender"]) for r in found["records"]}


class PublicBriefShape(unittest.TestCase):
    def test_every_record_kind_the_rules_name(self):
        found = mail_records(PUBLIC_BRIEF)
        self.assertEqual(len(found["records"]), 9)
        self.assertEqual(len([r for r in found["records"] if not r["subject"]]), 1)  # the approval: sender and meaning
        self.assertEqual(len(found["senders"]), 5)
        self.assertEqual(found["domain"], "")  # the brief names local parts only

    def test_technical_release_is_one_record(self):
        self.assertEqual(len(technical_records(PUBLIC_BRIEF)), 1)

    def test_reference(self):
        self.assertTrue(reference(PUBLIC_BRIEF))
        self.assertIn(reference(PUBLIC_BRIEF), PUBLIC_BRIEF.split("\n\n")[1])


class SyntheticBrief(unittest.TestCase):
    def test_renamed_subjects_and_senders(self):
        found = mail_records(SYNTHETIC)
        self.assertEqual(pairs(found), {("", "board"), ("Rabattmatrix", "pricing"), ("Hubfreigabe", "engineering"),
                                        ("Kartonsatz", "shipping"), ("Kursblatt", "treasury")})
        self.assertEqual(found["domain"], "example-pumps.test")
        self.assertNotIn("secret", " ".join(found["senders"]))  # logins are never parsed

    def test_prose_with_one_slash_is_not_a_record(self):
        subjects = {r["subject"] for r in mail_records(SYNTHETIC)["records"]}
        self.assertFalse(subjects & {"use the tender reference plus a subject", "Read the inbox"})

    def test_technical_release_from_the_stroke_rule(self):
        self.assertEqual([(r["subject"], r["sender"]) for r in technical_records(SYNTHETIC)],
                         [("Hubfreigabe", "engineering")])

    def test_reference(self):
        self.assertEqual(reference(SYNTHETIC), "TX-0001-0042")
        self.assertEqual(reference("Framework (2030) for pumps (TX-0001-0042)."), "TX-0001-0042")  # a year is no reference
        self.assertEqual(reference("Order (4711)."), "4711")  # a bare number when there is nothing else


class NeverRaises(unittest.TestCase):
    def test_empty_and_odd_briefs(self):
        for brief in ("", None, "no rules here", "a/b", "x@", "(", "@@@ ///"):
            self.assertIsInstance(mail_records(brief)["records"], list)
            self.assertIsInstance(technical_records(brief), list)
            self.assertIsInstance(reference(brief), str)
        self.assertEqual(mail_records("")["records"], [])

    def test_mission_falls_back_to_the_rules(self):
        self.assertIn("derive", wanted("no records named"))
        self.assertIn("Hubfreigabe", wanted(SYNTHETIC))


class TechnicalMailSelection(unittest.TestCase):
    def test_pages_of_the_technical_release_only(self):
        records = technical_records(SYNTHETIC)
        release = "From: engineering@example-pumps.test\nSubject: Hubfreigabe TX-0001-0042\nreserve 7 mm per end"
        other = "From: treasury@example-pumps.test\nSubject: Kursblatt TX-0001-0042\n1 USD = 0.9 EUR"
        self.assertTrue(mentions(release, records))
        self.assertFalse(mentions(other, records))
        self.assertFalse(mentions(release, []))  # nothing named: the resolver then takes all mail


if __name__ == "__main__":
    unittest.main()
