"""The dependency scheduler: specification-derived ERP searches overlap tender collection, but the later
requirements resolver remains authoritative. Synthetic agents stand in for browsers and models.

Run from the repo root: uv run --project agent --no-sync python -m unittest tests.test_schedule -v
"""
import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import agent  # noqa: E402


SPEC_A = {"bore_mm": 80, "stroke_mm": 200, "pressure_bar": 160, "mounting": "eye", "certification": "C1",
          "catalogue_group": "A"}
SPEC_B = {**SPEC_A, "catalogue_group": "B"}
SPEC_C = {**SPEC_A, "catalogue_group": "C"}


class FakePage:
    def __init__(self):
        self.context = self

    def on(self, *_):
        pass

    async def goto(self, *_, **__):
        pass

    async def new_page(self):
        return FakePage()


class FakePlaywright:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class Schedule(unittest.TestCase):
    def run_main(self, specs_answer: dict, spec_seconds: float = 0):
        """Run main with fake work; return its timing, cancelled searches and findings handed to calc."""
        events: list[tuple[str, float]] = []
        stopped: list[str] = []
        handed: dict = {}

        async def tender(*_):
            await asyncio.sleep(0.3)
            events.append(("tender done", time.time()))
            return {"evidence": ["tender page"]}

        async def quick(result):
            return result

        async def sites(_task):
            return {role: {"siteId": role, "url": "about:blank"}
                    for role in ("tender_portal", "supplier_portal", "erp", "webmail")}

        async def spec_agent(*_):
            await asyncio.sleep(spec_seconds)
            return {"evidence": ["specification page"]}

        async def specs(*_, effort="medium"):
            events.append(("specs asked", time.time()))
            return specs_answer

        async def requirements(*_, effort="medium"):
            return {"positions": [
                # Same values as A but written differently; C was not known to the early resolver.
                {"position": "1", "final_quantity_pieces": 5, **SPEC_A, "stroke_mm": "200.0", "mounting": "Eye"},
                {"position": "2", "final_quantity_pieces": 5, **SPEC_C}]}

        async def erp_run(_task, _tab, requirement, _deadline):
            group = requirement["catalogue_group"]
            events.append((f"search {group}", time.time()))
            try:
                await asyncio.sleep(100 if group == "B" else 0.02)
            except asyncio.CancelledError:
                stopped.append(group)
                raise
            return {"material_number": f"synthetic-{group}"}

        def bid(_tender, _requirements, _commercials, erp):
            handed.update(erp)
            return {"trace": "", "answer": {}, "omitted": []}

        async def connect(_playwright, _number=0):
            return None, FakePage()

        async def commercials(*_args, **_kwargs):
            return {"positions": []}

        patches = [
            mock.patch.object(agent, "async_playwright", FakePlaywright),
            mock.patch.object(agent.browsers, "cdp_urls", lambda: ["cdp"] * 4),
            mock.patch.object(agent.browsers, "connect", connect),
            mock.patch.object(agent.contract, "load_run", lambda: ({"run_id": "test"}, None)),
            mock.patch.object(agent.contract, "seconds_left", lambda _task: 1140),
            mock.patch.object(agent.resolvers, "sites", sites),
            mock.patch.object(agent.resolvers, "specs", specs),
            mock.patch.object(agent.resolvers, "requirements", requirements),
            mock.patch.object(agent.sweep, "commercials_with_sweep", commercials),
            mock.patch.object(agent.tender_portal, "run", tender),
            mock.patch.object(agent.supplier_portal, "run", spec_agent),
            mock.patch.object(agent.webmail, "run", lambda *_: quick({"evidence": ["technical release"]})),
            mock.patch.object(agent.erp_agent, "login", lambda *_: quick({"ok": True})),
            mock.patch.object(agent.erp_agent, "run", erp_run),
            mock.patch.object(agent, "bid", bid),
            mock.patch.object(agent.llm, "log", lambda *_: None),
            mock.patch.dict(os.environ, {"DRY_RUN": "1"}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

        self.assertEqual(asyncio.run(agent.main()), 0)
        return events, stopped, handed

    def test_early_searches_are_reused_and_unused_ones_stop(self):
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **SPEC_B}]})
        at = dict(events)
        self.assertLess(at["search A"], at["tender done"])
        self.assertGreater(at["search C"], at["tender done"])
        self.assertEqual([name for name, _ in events].count("search A"), 1)
        self.assertEqual(stopped, ["B"])
        self.assertEqual(handed, {"1": {"material_number": "synthetic-A"},
                                  "2": {"material_number": "synthetic-C"}})

    def test_without_governing_specs_searches_wait_for_requirements(self):
        events, stopped, handed = self.run_main({"requirements": []})
        at = dict(events)
        self.assertGreater(at["search A"], at["tender done"])
        self.assertEqual(stopped, [])
        self.assertEqual(handed, {"1": {"material_number": "synthetic-A"},
                                  "2": {"material_number": "synthetic-C"}})

    def test_tender_finishing_first_skips_competing_specs_resolver(self):
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}]}, spec_seconds=0.5)
        self.assertNotIn("specs asked", dict(events))
        self.assertEqual(stopped, [])
        self.assertEqual(handed, {"1": {"material_number": "synthetic-A"},
                                  "2": {"material_number": "synthetic-C"}})


if __name__ == "__main__":
    unittest.main()
