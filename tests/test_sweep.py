"""Gap sweep (I16): open facts are found by code, each starts one mission per website. Synthetic data, fake agents.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402
from agents.sweep import agent as sweep  # noqa: E402

TENDER = {"positions": [{"position": "1"}, {"position": "2"}]}
REQUIREMENTS = {"positions": [
    {"position": "1", "final_quantity_pieces": 10, "bore_mm": 40, "stroke_mm": 100, "pressure_bar": 160,
     "catalogue_group": "CG-1"},
    {"position": "2", "final_quantity_pieces": 5, "bore_mm": 50, "stroke_mm": 200, "pressure_bar": 160,
     "catalogue_group": "CG-2"}]}
COMMERCIALS = {"discount": {"percent": 3, "source": "approval message"}, "setup_pool_fee": 100,
               "project_bonus_bands": [{"from": 0, "to": None, "percent": 1}], "fx_rates": {"FX-1": 1.1},
               "metal_indices": {"IX-1": 2.0},
               "positions": [{"position": "1", "carton_price": 5, "setup_pool_member": True},
                             {"position": "2", "carton_price": 5, "project_bonus_member": True}]}
ERP = {"1": {"price_condition": {"currency": "USD", "fx_key": "FX-1"}, "surcharge_mass": "100 g",
             "price_index_key": "IX-1"}}


class Gaps(unittest.TestCase):
    def test_complete_first_pass_has_no_gaps(self):
        self.assertEqual(sweep.gaps(TENDER, REQUIREMENTS, COMMERCIALS, ERP), [])

    def test_one_unresolved_key_is_one_gap(self):
        commercials = {**COMMERCIALS, "fx_rates": {}}
        found = sweep.gaps(TENDER, REQUIREMENTS, commercials, ERP)
        self.assertEqual(len(found), 1)
        self.assertIn("FX rate", found[0]["fact"])
        self.assertEqual(found[0]["resolver"], "commercials")

    def test_missing_position_and_attribute(self):
        requirements = {"positions": [{**REQUIREMENTS["positions"][0], "stroke_mm": None}]}
        facts = [g["fact"] for g in sweep.gaps(TENDER, requirements, COMMERCIALS)]
        self.assertTrue(any("position 2" in f for f in facts))
        self.assertTrue(any("stroke_mm" in f for f in facts))

    def test_at_most_max_gaps(self):
        self.assertLessEqual(len(sweep.gaps({"positions": [{"position": str(i)} for i in range(9)]}, {}, {})),
                             sweep.MAX_GAPS)


class Sweep(unittest.TestCase):
    def setUp(self):
        self.investigate = llm.investigate

    def tearDown(self):
        llm.investigate = self.investigate

    def test_one_mission_per_gap_and_site_and_pages_go_to_the_resolver(self):
        calls = []

        async def fake(tab, system, mission, schema, deadline, tag, **kwargs):
            calls.append((tag, mission))
            found = tag == "sweep:erp"
            return {"found": found, "evidence": ["### rate page\nFX-1 = 1.1"] if found else []}
        llm.investigate = fake
        site = {"url": "https://site.test", "credentials": {"username": "u", "password": "p"}}
        tabs = {role: type("T", (), {"site": site})() for role in ("tender_portal", "erp", "webmail")}
        gap = [{"fact": "the FX rate (EUR per USD) for key FX-1", "resolver": "commercials"}]
        pages = asyncio.run(sweep.sweep({"brief": "# Task\n\n## Rules\n"}, tabs, gap, time.time() + 60))
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("FX rate" in m for _, m in calls))
        self.assertEqual(pages, {"commercials": ["### rate page\nFX-1 = 1.1"]})

    def test_never_two_missions_on_one_tab_at_once(self):
        busy, overlaps = set(), []

        async def fake(tab, system, mission, schema, deadline, tag, **kwargs):
            if tag in busy:
                overlaps.append(tag)
            busy.add(tag)
            await asyncio.sleep(0.01)
            busy.discard(tag)
            return {"found": False, "evidence": []}
        llm.investigate = fake
        site = {"url": "https://site.test", "credentials": {"username": "u", "password": "p"}}
        tabs = {role: type("T", (), {"site": site})() for role in ("tender_portal", "webmail")}
        gap_list = [{"fact": "fact one", "resolver": "commercials"}, {"fact": "fact two", "resolver": "commercials"}]
        asyncio.run(sweep.sweep({"brief": "# Task\n\n## Rules\n"}, tabs, gap_list, time.time() + 60))
        self.assertEqual(overlaps, [])


if __name__ == "__main__":
    unittest.main()
