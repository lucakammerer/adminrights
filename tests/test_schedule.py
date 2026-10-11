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
    def run_main(self, specs_answer: dict, spec_seconds: float = 0, positions: list | None = None):
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
            return {"positions": positions or [  # 1 has R1's values written differently, 2 values no early search had
                {"position": "1", "final_quantity_pieces": 5, **SPEC_A, "stroke_mm": "200.0", "mounting": "Eye"},
                {"position": "2", "final_quantity_pieces": 5, **SPEC_C}]}

        async def erp_run(task, tab, req, deadline, news=None):
            group = req["catalogue_group"]
            events.append((f"search {group}", time.time()))
            if group == "E":  # decides "no match" on the old values at once; its check is told of the change
                if [name for name, _ in events].count("search E") == 1:
                    return {"material_number": "", "no_match": True}
                for _ in range(40):
                    if news:
                        return {"material_number": "M-E", "stroke_mm": req["stroke_mm"], "told": news.pop(0)}
                    await asyncio.sleep(0.05)
                return {"material_number": "", "no_match": True}
            try:
                first = [name for name, _ in events].count(f"search {group}") == 1
                if group in ("B", "D") and news is not None and first:  # runs until told of a changed requirement
                    while not news:
                        await asyncio.sleep(0.05)
                    if group == "B":  # read before its next step; D had already decided and never reads it
                        events.append((news.pop(0), time.time()))
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                stopped.append(group)
                raise
            stale = group == "D" and news
            return {"material_number": f"M-{group}" + ("-old" if stale else ""), "stroke_mm": req["stroke_mm"]}

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
        self.assertEqual({p: r["material_number"] for p, r in handed.items()}, {"1": "M-A", "2": "M-C"})

    def test_a_changed_requirement_goes_to_the_running_search_of_its_group(self):
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **SPEC_B}]},
            positions=[{"position": "1", "final_quantity_pieces": 5, **SPEC_A},
                       {"position": "2", "final_quantity_pieces": 5, **SPEC_B, "stroke_mm": 300}])
        names = [name for name, _ in events]
        self.assertEqual(names.count("search B"), 1)  # not started over
        self.assertTrue(any("changed" in name and "300" in name for name in names))
        self.assertEqual(stopped, [])
        self.assertEqual(handed["2"], {"material_number": "M-B", "stroke_mm": 300})

    def test_a_search_that_decided_before_the_change_is_run_again(self):
        spec_d = {**SPEC_A, "catalogue_group": "D"}
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **spec_d}]},
            positions=[{"position": "1", "final_quantity_pieces": 5, **SPEC_A},
                       {"position": "2", "final_quantity_pieces": 5, **spec_d, "stroke_mm": 300}])
        self.assertEqual([name for name, _ in events].count("search D"), 2)
        self.assertEqual(handed["2"], {"material_number": "M-D", "stroke_mm": 300})

    def test_a_change_during_the_no_match_check_reaches_the_check(self):
        spec_e = {**SPEC_A, "catalogue_group": "E"}
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **spec_e}]},
            positions=[{"position": "1", "final_quantity_pieces": 5, **SPEC_A},
                       {"position": "2", "final_quantity_pieces": 5, **spec_e, "stroke_mm": 300}])
        self.assertEqual(handed["2"]["material_number"], "M-E")
        self.assertEqual(handed["2"]["stroke_mm"], 300)

    def test_without_specs_the_searches_wait_for_the_requirements(self):
        events, stopped, handed = self.run_main({"requirements": []})
        at = dict(events)
        self.assertGreater(at["search A"], at["tender done"])
        self.assertEqual(stopped, [])
        self.assertEqual({p: r["material_number"] for p, r in handed.items()}, {"1": "M-A", "2": "M-C"})

    def test_no_specs_call_once_the_tender_agent_is_done(self):
        # the specification comes in after the tender: requirements starts at once, a specs call would only compete
        events, stopped, handed = self.run_main(
            {"requirements": [{"requirement": "R1", **SPEC_A}, {"requirement": "R2", **SPEC_B}]}, spec_seconds=0.8)
        self.assertNotIn("specs asked", dict(events))
        self.assertEqual(stopped, [])
        self.assertEqual({p: r["material_number"] for p, r in handed.items()}, {"1": "M-A", "2": "M-C"})


if __name__ == "__main__":
    unittest.main()
