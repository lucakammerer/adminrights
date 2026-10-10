"""An ERP no_match needs proof on kept pages before it can become a no_bid (rules 3, 8): synthetic pages, fake model.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402
from agents.erp import agent as erp  # noqa: E402

TASK = {"brief": "# Task\nA synthetic brief.\n\n## Rules\n\n3. Material: an exact match."}
REQUIREMENT = {"bore_mm": 40, "stroke_mm": 150, "pressure_bar": 160, "mounting": "flange", "certification": "none",
               "catalogue_group": "CG-1"}
RESULTS_PAGE = "Fetched /search?q=CG-1 (HTTP 200)\nMAT-1 40/175 flange\nMAT-2 40/150 flange status blocked"
PROVEN = {"material_number": "", "no_match": True, "why": "none qualifies",
          "candidates": [{"material": "MAT-1", "differs_in": "stroke"}, {"material": "MAT-2", "blocked": True}]}


class Call:
    def __init__(self, name, args, n):
        self.id = f"call-{n}"
        self.function = type("F", (), {"name": name, "arguments": json.dumps(args)})()


class Reply:
    def __init__(self, calls):
        message = type("M", (), {})()
        message.content = ""
        message.tool_calls = calls
        message.model_dump = lambda exclude_none=True: {"role": "assistant", "content": ""}
        self.choices = [type("C", (), {"message": message})()]


class FakeTab:
    site = {"url": "https://erp.test", "credentials": {"username": "u", "password": "p"}}

    async def read(self, offset=0):
        return "URL: https://erp.test/\nmain screen"

    async def fetch(self, url):
        return RESULTS_PAGE


def scripted(turns):
    """A fake model that plays the given turns (lists of (tool, args)) and records what it was told."""
    told: list[str] = []
    seen: set[int] = set()
    queue = list(turns)

    async def chat(messages, tools=None, **kwargs):
        for m in messages:  # the model sees the whole history each turn: record every tool answer once
            if isinstance(m, dict) and m.get("role") == "tool" and id(m) not in seen:
                seen.add(id(m))
                told.append(m["content"])
        calls = queue.pop(0) if queue else [("finish", {"result": PROVEN})]
        return Reply([Call(name, args, i) for i, (name, args) in enumerate(calls)])
    return chat, told


class Unproven(unittest.TestCase):
    def test_reasons(self):
        self.assertIn("needs proof", erp.unproven(PROVEN, []))
        self.assertIn("list every candidate", erp.unproven({"no_match": True}, [RESULTS_PAGE]))
        self.assertIn("MAT-9", erp.unproven({"candidates": [{"material": "MAT-9"}]}, [RESULTS_PAGE]))
        self.assertEqual(erp.unproven(PROVEN, [RESULTS_PAGE]), "")


class NoMatchFinish(unittest.TestCase):
    def setUp(self):
        self.chat = llm.chat

    def tearDown(self):
        llm.chat = self.chat

    def run_agent(self, turns):
        llm.chat, told = scripted(turns)
        result = asyncio.run(erp.run(TASK, FakeTab(), REQUIREMENT, time.time() + 600))
        return result, told

    def test_unproven_no_match_is_sent_back_then_proven(self):
        result, told = self.run_agent([
            [("finish", {"result": {"material_number": "", "no_match": True, "why": "nothing found"}})],
            [("save_evidence", {"url": "/search?q=CG-1", "label": "results"})],
            [("finish", {"result": PROVEN})]])
        self.assertTrue(any("needs proof" in t for t in told))
        self.assertTrue(result.get("no_match"))
        self.assertEqual(len(result["evidence"]), 1)
        self.assertFalse(result.get("forced"))

    def test_unprovable_no_match_goes_through_after_two_refusals(self):
        bare = [("finish", {"result": {"material_number": "", "no_match": True, "why": "nothing"}})]
        result, told = self.run_agent([bare, bare, bare])
        self.assertEqual(sum("needs proof" in t for t in told), erp.NO_MATCH_REFUSALS)
        self.assertTrue(result.get("no_match"))  # main's second agent still has to confirm it


if __name__ == "__main__":
    unittest.main()
