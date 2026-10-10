"""calc against the public-1 reference, and against model output written as text (I10, I14, I15).

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import copy
import json
import sys
import unittest
from decimal import Decimal
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

    def test_known_material_without_prices_is_submitted(self):
        """Rule 9: material, quantity, surcharge, packaging and lead time keep their points; base stays blank."""
        facts = copy.deepcopy(FACTS)
        unpriced = facts["positions"][0]
        unpriced["scales"] = []
        result = calc.compute(facts)
        self.assertEqual(result["omitted"], [])
        row = next(p for p in result["answer"]["positions"] if p["position"] == unpriced["position"])
        self.assertNotIn("base_unit_price", row)
        omitted = copy.deepcopy(FACTS)
        omitted["positions"][0]["material_number"] = None
        self.assertGreater(quality(facts), quality(omitted))


def synthetic(**position):
    """One synthetic position at 10.00 EUR per piece, nothing else priced."""
    base = {"position": "1", "quantity_pieces": 10, "material_number": "M", "scales": [{"min_quantity": 1, "price": 10}],
            "stock": 100, "lead_time_stock_weeks": 1, "lead_time_production_weeks": 9}
    return {"tender_reference": "T", "positions": [{**base, **position}]}


class Edges(unittest.TestCase):
    def test_discount_threshold_is_inclusive(self):
        facts = synthetic()
        facts["discount"] = {"percent": 10, "min_order_value": 100}
        self.assertEqual(calc.compute(facts)["answer"]["discount_percent"], 10.0)
        facts["discount"]["min_order_value"] = 100.01
        self.assertEqual(calc.compute(facts)["answer"]["discount_percent"], 0.0)

    def test_delivery_ceiling_is_inclusive_over_shared_demand(self):
        commitment = {"material_number": "M", "max_pieces": 20, "weeks": 3}
        facts = synthetic(delivery_commitment=commitment)
        facts["positions"].append({**facts["positions"][0], "position": "2"})
        self.assertEqual({p["lead_time_weeks"] for p in calc.compute(facts)["answer"]["positions"]}, {3})
        commitment["max_pieces"] = 19
        self.assertEqual({p["lead_time_weeks"] for p in calc.compute(facts)["answer"]["positions"]}, {1})

    def test_stock_is_shared_across_positions(self):
        facts = synthetic(stock=15)
        facts["positions"].append({**facts["positions"][0], "position": "2"})
        self.assertEqual({p["lead_time_weeks"] for p in calc.compute(facts)["answer"]["positions"]}, {9})

    def test_bonus_bands_are_marginal(self):
        bands = [{"from": 0, "to": 100, "percent": 0}, {"from": 100, "to": None, "percent": 10}]
        self.assertEqual(calc.bonus_credit(Decimal("100"), bands), Decimal("0.00"))
        self.assertEqual(calc.bonus_credit(Decimal("150"), bands), Decimal("5.00"))

    def test_allocation_leftover_cents_go_to_largest_remainder_then_position(self):
        self.assertEqual(calc.allocate(Decimal("1.00"), {"a": Decimal(1), "b": Decimal(1), "c": Decimal(1)}),
                         {"a": Decimal("0.34"), "b": Decimal("0.33"), "c": Decimal("0.33")})
        self.assertEqual(calc.allocate(Decimal("1.00"), {"a": Decimal(1), "b": Decimal(2)}),
                         {"a": Decimal("0.33"), "b": Decimal("0.67")})


class Parsing(unittest.TestCase):
    def test_grams_to_kg(self):
        for text, kg in [("2125 g", 2.125), ("2.125 g", 2.125), ("2,125 g", 2.125), ("2125 Gramm", 2.125),
                         ("125,5 g", 0.1255), ("1,375 kg", 1.375), ("1.375 kg", 1.375), ("1.234,5 kg", 1234.5)]:
            self.assertAlmostEqual(calc.grams_to_kg(text), kg, msg=text)

    def test_number_trusts_its_own_format_over_the_hint(self):
        for text, fmt, value in [("2,743.58", "de-DE", 2743.58), ("2.743,58", "en-US", 2743.58),
                                 ("1.234.567", "en-US", 1234567), ("186,615", "en-US", 186615),
                                 ("186,615", "de-DE", 186.615), ("1,0873", "", 1.0873)]:
            self.assertAlmostEqual(calc.number(text, fmt), value, msg=f"{text} {fmt}")

    def test_rate_lookup_tolerates_key_spelling(self):
        rates = {"FX-1": 1.1, "FX-2": 0.9}
        self.assertEqual(calc.lookup(rates, "fx 2"), 0.9)
        self.assertEqual(calc.lookup(rates, "FX-2 (USD)"), 0.9)
        self.assertEqual(calc.lookup({"USD": 1.2, "GBP": 1.4}, "FX-9", "USD"), 1.2)
        self.assertIsNone(calc.lookup(rates, "FX-3"))


if __name__ == "__main__":
    unittest.main()
