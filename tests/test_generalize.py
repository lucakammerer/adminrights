"""Generalization (I16, I12, rules 10, 19): records on an unexpected website still reach the resolver that needs them,
the sweep looks for open facts during the ERP stage without risking the first answer, ERP searches stay bounded and
don't loop on facts only some rules need. Synthetic data, fake models.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402
from agents.erp import agent as erp  # noqa: E402
from agents.resolvers import agent as resolvers  # noqa: E402
from agents.sweep import agent as sweep  # noqa: E402

BRIEF = """# Task
Bid for pumps (TX-0001-0042).

## Rules

5. Discount: the latest message from board@ approving a discount for this exact reference.

## Additional rules

- Authority: authorized subjects/senders: Hubfreigabe/engineering, Kartonsatz/shipping.
- Stroke derivation: add twice the end reserve given in the Hubfreigabe.
"""
TASK = {"brief": BRIEF}
TENDER = {"positions": [{"position": "01.01"}, {"position": "01.02"}], "evidence": ["### tender page\nTX-0001-0042"]}
SPEC = {"evidence": ["### requirement sheet\nbore 40", "### stray approval\nKartonsatz TX-0001-0042: 4.50 per carton"]}
MAIL = {"evidence": ["### release\nengineering@x.test Hubfreigabe: reserve 5 mm",
                     "### clarification\nPosition 01.02: quantity now 12 pieces",
                     "### unrelated\nnewsletter"]}


class Asked:
    """A fake ask_json that records the questions and answers with a fixed object."""

    def __init__(self, answer):
        self.answer, self.questions = answer, []

    async def __call__(self, system, question, effort=None):
        self.questions.append(question)
        return dict(self.answer)


class ResolverRouting(unittest.TestCase):
    def setUp(self):
        self.ask_json = llm.ask_json

    def tearDown(self):
        llm.ask_json = self.ask_json

    def test_requirements_get_the_technical_release_and_mail_about_positions(self):
        llm.ask_json = asked = Asked({"positions": []})
        asyncio.run(resolvers.requirements(TASK, TENDER, SPEC, MAIL))
        question = asked.questions[0]
        self.assertIn("reserve 5 mm", question)
        self.assertIn("quantity now 12 pieces", question)
        self.assertNotIn("newsletter", question)

    def test_commercials_get_a_record_found_on_another_website(self):
        llm.ask_json = asked = Asked({})
        asyncio.run(resolvers.commercials(TASK, TENDER, MAIL, [SPEC]))
        self.assertIn("4.50 per carton", asked.questions[0])
        self.assertNotIn("bore 40", asked.questions[0])

    def test_nothing_routed_leaves_the_prompt_as_before(self):
        llm.ask_json = asked = Asked({})
        asyncio.run(resolvers.commercials(TASK, TENDER, MAIL, [{"evidence": ["### sheet\nbore 40"]}]))
        asyncio.run(resolvers.commercials(TASK, TENDER, MAIL))
        self.assertEqual(asked.questions[0], asked.questions[1])
        self.assertNotIn("other websites", asked.questions[1])


class ErpExtract(unittest.TestCase):
    def setUp(self):
        self.ask_json = llm.ask_json

    def tearDown(self):
        llm.ask_json = self.ask_json

    FACTS = {"material_number": "M-1", "available_stock_pieces": 4, "lead_time_stock_weeks": 1,
             "lead_time_production_weeks": 6, "price_condition": {"scales": [{"from_quantity": 1, "price_as_shown": "9,50"}]}}

    def test_facts_only_some_rules_need_are_asked_for_once(self):
        llm.ask_json = Asked(self.FACTS)
        asked: set = set()
        _, first = asyncio.run(erp.extract(TASK, {}, {"material_number": "M-1"}, ["page"], asked))
        _, second = asyncio.run(erp.extract(TASK, {}, {"material_number": "M-1"}, ["page"], asked))
        self.assertIn("pieces_per_carton", first)
        self.assertEqual(second, "")

    def test_core_facts_are_always_asked_for(self):
        llm.ask_json = Asked({**self.FACTS, "price_condition": {}})
        asked: set = set()
        for _ in range(2):
            _, problem = asyncio.run(erp.extract(TASK, {}, {"material_number": "M-1"}, ["page"], asked))
            self.assertIn("price scales", problem)


class ErpParallel(unittest.TestCase):
    def setUp(self):
        self.investigate = llm.investigate

    def tearDown(self):
        llm.investigate = self.investigate

    def test_at_most_parallel_searches_at_once(self):
        running, peak = [0], [0]

        async def fake(*args, **kwargs):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.01)
            running[0] -= 1
            return {"material_number": "", "evidence": []}
        llm.investigate = fake
        tab = type("T", (), {"site": {"url": "https://erp.test", "credentials": {"username": "u", "password": "p"}}})()

        async def many():
            await asyncio.gather(*(erp.run(TASK, tab, {"catalogue_group": f"G{i}"}, time.time() + 60) for i in range(15)))
        asyncio.run(many())
        self.assertEqual(peak[0], erp.PARALLEL)


class CommercialsWithSweep(unittest.TestCase):
    def setUp(self):
        self.commercials, self.sweep = resolvers.commercials, sweep.sweep

    def tearDown(self):
        resolvers.commercials, sweep.sweep = self.commercials, self.sweep

    COMPLETE = {"discount": {"percent": 3, "source": "approval"}, "positions": [{"position": "01.01", "carton_price": 4}]}
    OPEN = {"discount": {"percent": 3, "source": "approval"}, "positions": [{"position": "01.01", "carton_price": 0}]}

    def run_it(self, answers, swept, until_in=600):
        calls, opened = [], []

        async def commercials(task, tender, mail, others=None):
            calls.append(tender)
            answer = answers[min(len(calls), len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer

        async def fake_sweep(task, tabs, gap_list, until):
            return swept

        async def open_tabs():
            opened.append(True)
            return {}
        resolvers.commercials, sweep.sweep = commercials, fake_sweep
        result = asyncio.run(sweep.commercials_with_sweep(TASK, TENDER, MAIL, [], open_tabs, time.time() + until_in))
        return result, calls, opened

    def test_nothing_open_means_no_sweep(self):
        result, calls, opened = self.run_it([self.COMPLETE], {})
        self.assertEqual((result, len(calls), opened), (self.COMPLETE, 1, []))

    def test_swept_pages_reach_the_second_call(self):
        result, calls, opened = self.run_it([self.OPEN, self.COMPLETE], {"commercials": ["### tariff\n4 per carton"]})
        self.assertEqual(result, self.COMPLETE)
        self.assertIn("### tariff\n4 per carton", calls[1]["evidence"])

    def test_a_sweep_still_running_when_the_erp_searches_are_done_stops_at_once(self):
        async def commercials(task, tender, mail, others=None):
            return self.OPEN

        async def slow_sweep(task, tabs, gap_list, until):
            await asyncio.sleep(30)
            return {"commercials": ["page"]}

        async def open_tabs():
            return {}

        async def scenario():
            stop = asyncio.Event()
            job = asyncio.ensure_future(sweep.commercials_with_sweep(TASK, TENDER, MAIL, [], open_tabs,
                                                                     time.time() + 600, stop))
            await asyncio.sleep(0.05)
            stop.set()  # agent.main: the ERP searches are done
            started = time.time()
            result = await job
            return result, time.time() - started
        resolvers.commercials, sweep.sweep = commercials, slow_sweep
        result, waited = asyncio.run(scenario())
        self.assertEqual(result, self.OPEN)
        self.assertLess(waited, 1)

    def test_the_first_answer_survives(self):
        for answers, swept, until_in in (([self.OPEN, RuntimeError("model down")], {"commercials": ["page"]}, 600),
                                         ([self.OPEN], {}, 600),            # the sweep found nothing
                                         ([self.OPEN], {"commercials": ["page"]}, 100)):  # no time for a sweep
            result, _, _ = self.run_it(answers, swept, until_in)
            self.assertEqual(result, self.OPEN)


if __name__ == "__main__":
    unittest.main()
