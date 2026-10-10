"""Brief parsing (I12): mail records, the technical release and the reference come from the run's brief, never from code.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from agents.common import (commercial_records, mail_records, mentions, names_position, reference, routed,  # noqa: E402
                           technical_records)
from agents.webmail.agent import groups, wanted  # noqa: E402

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


# The same rules in other list shapes a private brief may use.
VARIANTS = """## Additional rules

- Authority: records come from these senders: Preisblatt (pricing), Lieferplan (logistics@<domain>); Kursliste from treasury@.
- Approvals: Rabattvorlage by board@<domain> and Abnahme from quality@.
- Stroke derivation: add twice the reserve of the Lieferplan record.
"""


class OtherListShapes(unittest.TestCase):
    def test_parenthesised_and_from_forms(self):
        self.assertEqual(pairs(mail_records(VARIANTS)), {("Preisblatt", "pricing"), ("Lieferplan", "logistics"),
                                                        ("Kursliste", "treasury"), ("Rabattvorlage", "board"),
                                                        ("Abnahme", "quality")})

    def test_commercial_records_leave_out_the_technical_one(self):
        self.assertEqual([(r["subject"], r["sender"]) for r in technical_records(VARIANTS)], [("Lieferplan", "logistics")])
        self.assertNotIn("Lieferplan", {r["subject"] for r in commercial_records(VARIANTS)})


class Routing(unittest.TestCase):
    def test_names_position(self):
        self.assertTrue(names_position("Quantity for position 01.05 is now 30", ["01.05"]))
        self.assertFalse(names_position("Quantity for position 01.050", ["01.05"]))
        self.assertFalse(names_position("Item 1 of the list", ["1"]))  # too short to tell apart from any number

    def test_routed_pages_of_other_websites(self):
        others = [{"evidence": ["### a\nPreisblatt for TX-1", "### b\nrequirement sheet"]}, {}, "not a result"]
        self.assertEqual(routed(others, lambda page: "Preisblatt" in page), ["### a\nPreisblatt for TX-1"])


class NeverRaises(unittest.TestCase):
    def test_empty_and_odd_briefs(self):
        for brief in ("", None, "no rules here", "a/b", "x@", "(", "@@@ ///"):
            self.assertIsInstance(mail_records(brief)["records"], list)
            self.assertIsInstance(technical_records(brief), list)
            self.assertIsInstance(reference(brief), str)
        self.assertEqual(mail_records("")["records"], [])

    def test_mission_falls_back_to_the_rules(self):
        self.assertIn("derive", wanted(mail_records("no records named")["records"]))
        self.assertIn("Hubfreigabe", wanted(mail_records(SYNTHETIC)["records"]))

    def test_mail_agents_share_every_record_the_technical_release_first(self):
        shares = groups(SYNTHETIC)
        self.assertEqual(shares[0], technical_records(SYNTHETIC))
        self.assertCountEqual([r for share in shares for r in share], mail_records(SYNTHETIC)["records"])


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
