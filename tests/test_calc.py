"""calc against the public-1 reference, and against model output written as text (I10, I14, I15).

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))

import calc  # noqa: E402
import compare  # noqa: E402

FACTS = json.loads((ROOT / "tests/fixtures/facts.json").read_text())
EXPECTED = json.loads((ROOT / "eval/expected.json").read_text())


def quality(facts) -> float:
    return float(compare.score(calc.compute(facts)["answer"], EXPECTED)[1])


class Golden(unittest.TestCase):
    def test_complete_facts_score_100(self):
        self.assertEqual(quality(FACTS), 100.0)

    def test_values_written_as_text_score_100(self):
        """facts passes these through as the model wrote them."""
        facts = copy.deepcopy(FACTS)
        for p in facts["positions"]:
            p["pieces_per_carton"] = f"{p['pieces_per_carton']} Stück"
            p["lead_time_stock_weeks"] = f"{p['lead_time_stock_weeks']} Wochen"
            p["stock"] = f"{p['stock']} ST"
            if p.get("delivery_commitment"):
                p["delivery_commitment"]["max_pieces"] = f"max. {p['delivery_commitment']['max_pieces']} Stück"
        self.assertEqual(quality(facts), 100.0)

    def test_nothing_finished_still_answers(self):
        facts = copy.deepcopy(FACTS)
        for p in facts["positions"]:
            p["material_number"] = None
        result = calc.compute(facts)
        self.assertEqual(result["answer"]["positions"], [])
        self.assertEqual(result["answer"]["tender_reference"], FACTS["tender_reference"])
        self.assertEqual(len(result["omitted"]), len(FACTS["positions"]))


class Parsing(unittest.TestCase):
    def test_grams_to_kg(self):
        for text, kg in [("2125 g", 2.125), ("2.125 g", 2.125), ("2,125 g", 2.125), ("2125 Gramm", 2.125),
                         ("125,5 g", 0.1255), ("1,375 kg", 1.375), ("1.375 kg", 1.375), ("1.234,5 kg", 1234.5)]:
            self.assertAlmostEqual(calc.grams_to_kg(text), kg, msg=text)

    def test_rate_lookup_tolerates_key_spelling(self):
        rates = {"FX-1": 1.1, "FX-2": 0.9}
        self.assertEqual(calc.lookup(rates, "fx 2"), 0.9)
        self.assertEqual(calc.lookup(rates, "FX-2 (USD)"), 0.9)
        self.assertEqual(calc.lookup({"USD": 1.2, "GBP": 1.4}, "FX-9", "USD"), 1.2)
        self.assertIsNone(calc.lookup(rates, "FX-3"))


if __name__ == "__main__":
    unittest.main()
