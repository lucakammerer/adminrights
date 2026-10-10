"""The phase order of agent.main, with fake agents instead of sites and models: the ERP searches start from the specs
resolver while the tender agent is still working, a position with the same values reuses its search, a position with
other values gets a search of its own, and a search no position needs is stopped.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
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
        """agent.main with fake agents; returns the (event, time) list, the stopped searches and the ERP findings."""
        events: list[tuple[str, float]] = []
        stopped: list[str] = []
        handed: dict = {}

        async def tender(*_):
            await asyncio.sleep(0.5)
            events.append(("tender done", time.time()))
            return {"evidence": ["tender page"]}

        async def quick(result):
            return result

        async def sites(task):
            return {role: {"siteId": role, "url": "about:blank"}
                    for role in ("tender_portal", "supplier_portal", "erp", "webmail")}

        async def spec_agent(*_):
            await asyncio.sleep(spec_seconds)
            return {"evidence": ["spec page"]}

        async def specs(*_, effort="medium"):
            events.append(("specs asked", time.time()))
            return specs_answer

        async def requirements(*_, effort="medium"):
            return {"positions": [  # 1 has R1's values written differently, 2 values no early search had
                {"position": "1", "final_quantity_pieces": 5, **SPEC_A, "stroke_mm": "200.0", "mounting": "Eye"},
                {"position": "2", "final_quantity_pieces": 5, **SPEC_C}]}

        async def erp_run(task, tab, req, deadline):
            group = req["catalogue_group"]
            events.append((f"search {group}", time.time()))
            try:
                await asyncio.sleep(100 if group == "B" else 0.1)
            except asyncio.CancelledError:
                stopped.append(group)
                raise
            return {"material_number": f"M-{group}"}

        def bid(tender_result, requirements_result, commercials, erp):
            handed.update(erp)
            return {"trace": "", "answer": {}, "omitted": []}

        async def connect(playwright, number=0):
            return None, FakePage()

        patches = [
            mock.patch.object(agent, "async_playwright", FakePlaywright),
            mock.patch.object(agent.browsers, "cdp_urls", lambda: ["cdp"] * 4),
            mock.patch.object(agent.browsers, "connect", connect),
            mock.patch.object(agent.contract, "load_run", lambda: ({"run_id": "test", "brief": ""}, None)),
            mock.patch.object(agent.contract, "seconds_left", lambda task: 1140),
            mock.patch.object(agent.resolvers, "sites", sites),
            mock.patch.object(agent.resolvers, "specs", specs),
            mock.patch.object(agent.resolvers, "requirements", requirements),
            mock.patch.object(agent.resolvers, "commercials", lambda *_: quick({"positions": []})),
            mock.patch.object(agent.tender_portal, "run", tender),
            mock.patch.object(agent.supplier_portal, "run", spec_agent),
            mock.patch.object(agent.webmail, "run", lambda *_: quick({"evidence": ["technical mail"]})),
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

    def test_erp_searches_start_before_the_tender_agent_is_done(self):
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **SPEC_B}]})
        at = dict(events)
        self.assertLess(at["search A"], at["tender done"])  # started from the specs, not after the requirements
        self.assertGreater(at["search C"], at["tender done"])  # only the requirements named C
        self.assertEqual([name for name, _ in events].count("search A"), 1)  # position 1 reused A's search
        self.assertEqual(stopped, ["B"])  # no position needed B
        self.assertEqual(handed, {"1": {"material_number": "M-A"}, "2": {"material_number": "M-C"}})

    def test_without_specs_the_searches_wait_for_the_requirements(self):
        events, stopped, handed = self.run_main({"requirements": []})
        at = dict(events)
        self.assertGreater(at["search A"], at["tender done"])
        self.assertEqual(stopped, [])
        self.assertEqual(handed, {"1": {"material_number": "M-A"}, "2": {"material_number": "M-C"}})

    def test_no_specs_call_once_the_tender_agent_is_done(self):
        # the specification comes in after the tender: requirements starts at once, a specs call would only compete
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **SPEC_B}]}, spec_seconds=0.8)
        self.assertNotIn("specs asked", dict(events))
        self.assertEqual(stopped, [])
        self.assertEqual(handed, {"1": {"material_number": "M-A"}, "2": {"material_number": "M-C"}})


if __name__ == "__main__":
    unittest.main()
