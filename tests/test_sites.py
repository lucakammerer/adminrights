"""resolvers.sites with a fake model: every role gets a website and nothing raises (F21, I3).

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402
from agents.resolvers import agent as resolvers  # noqa: E402

ROLES = list(resolvers.ROLES)


def task(submission_site="a"):
    """Four synthetic websites; the bid goes to `submission_site`."""
    access = [{"siteId": i, "url": f"https://{i}.example", "credentials": {}} for i in ("a", "b", "c", "d")]
    submission = {"kind": "site", "siteId": submission_site, "url": "https://a.example"} if submission_site \
        else {"kind": "api", "url": "https://api.example/answer"}
    return {"brief": "# Synthetic task\n", "access": access, "submission": submission}


class FakeModel:
    """Replaces llm.ask_json: hands out the given answers in order (an exception instance is raised)."""

    def __init__(self, *answers, delay=0.0):
        self.answers = list(answers)
        self.delay = delay
        self.calls = 0
        self.prompts = []

    async def __call__(self, system, user, effort=None):
        self.calls += 1
        self.prompts.append(user)
        await asyncio.sleep(self.delay)
        answer = self.answers[min(self.calls, len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


class SitesTest(unittest.TestCase):
    def setUp(self):
        self.ask_json, self.log, self.timeout = llm.ask_json, llm.log, resolvers.SITES_TIMEOUT
        llm.log = lambda tag, text: None

    def tearDown(self):
        llm.ask_json, llm.log, resolvers.SITES_TIMEOUT = self.ask_json, self.log, self.timeout

    def run_sites(self, model, t=None):
        llm.ask_json = model
        roles = asyncio.run(resolvers.sites(t or task()))
        ids = {role: entry["siteId"] for role, entry in roles.items()}
        self.assertEqual(list(ids), ROLES)  # every role, in the fixed order main pairs with browsers
        self.assertEqual(len(set(ids.values())), len(ROLES))  # four sites, four distinct roles
        return ids

    def test_model_answer_is_used(self):
        ids = self.run_sites(FakeModel({"tender_portal": "a", "supplier_portal": "c", "erp": "d", "webmail": "b"}))
        self.assertEqual(ids, {"tender_portal": "a", "supplier_portal": "c", "erp": "d", "webmail": "b"})

    def test_model_failure_never_raises(self):
        model = FakeModel(RuntimeError("model down"))
        ids = self.run_sites(model)
        self.assertEqual(model.calls, 2)
        self.assertEqual(ids["tender_portal"], "a")  # the submission target still pins the tender portal

    def test_timeout_falls_back_to_elimination(self):
        resolvers.SITES_TIMEOUT = 0.05
        ids = self.run_sites(FakeModel({"tender_portal": "a"}, delay=1.0))
        self.assertEqual(ids["tender_portal"], "a")

    def test_submission_target_beats_the_model(self):
        ids = self.run_sites(FakeModel({"tender_portal": "b", "supplier_portal": "a", "erp": "c", "webmail": "d"}))
        self.assertEqual(ids["tender_portal"], "a")
        self.assertEqual(ids["supplier_portal"], "b")  # "a" was taken; the only site left goes to the open role

    def test_unknown_duplicate_and_non_text_ids_are_ignored(self):
        ids = self.run_sites(FakeModel({"tender_portal": "a", "supplier_portal": "zzz", "erp": "a", "webmail": ["d"]}))
        self.assertEqual(ids["tender_portal"], "a")

    def test_partial_answers_are_merged_across_attempts(self):
        model = FakeModel({"supplier_portal": "b"}, {"erp": "c", "webmail": "d"})
        ids = self.run_sites(model)
        self.assertEqual(ids, {"tender_portal": "a", "supplier_portal": "b", "erp": "c", "webmail": "d"})
        self.assertEqual(model.calls, 2)
        retry = model.prompts[1]
        self.assertIn("supplier_portal is already b", retry)
        self.assertNotIn('"supplier_portal": "<siteId>"', retry)

    def test_without_a_submission_site_the_model_decides(self):
        ids = self.run_sites(FakeModel({"tender_portal": "d", "supplier_portal": "c", "erp": "b", "webmail": "a"}),
                             task(submission_site=None))
        self.assertEqual(ids, {"tender_portal": "d", "supplier_portal": "c", "erp": "b", "webmail": "a"})



class FirstTest(unittest.TestCase):
    def test_a_failed_call_leaves_the_answer_to_the_other(self):
        async def fails():
            raise TimeoutError("hung")

        async def answers():
            await asyncio.sleep(0.01)
            return {"positions": []}

        self.assertEqual(asyncio.run(resolvers.first(fails(), answers())), {"positions": []})
        with self.assertRaises(TimeoutError):
            asyncio.run(resolvers.first(fails(), fails()))


class CommercialsTest(unittest.TestCase):
    def setUp(self):
        self.ask_json, self.log = llm.ask_json, llm.log
        llm.log = lambda tag, text: None

    def tearDown(self):
        llm.ask_json, llm.log = self.ask_json, self.log

    def test_an_answer_without_positions_is_asked_once_more(self):
        partial, full = {"discount": {"percent": 3}}, {"discount": {"percent": 3}, "positions": [{"position": "1"}]}
        tender = {"positions": [{"position": "1"}]}
        for answers, want, calls in (((full,), full, 1), ((partial, full), full, 2), ((partial, partial), partial, 2),
                                     ((partial, TimeoutError("hung")), partial, 2)):
            llm.ask_json = FakeModel(*answers)
            self.assertEqual(asyncio.run(resolvers.commercials(task(), tender, {})), want)
            self.assertEqual(llm.ask_json.calls, calls)

if __name__ == "__main__":
    unittest.main()
