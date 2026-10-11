"""The submission in two stages (I6): the first enters only what needs no bid, the second continues from it, and the
TAN look-up starts from the mailbox pages the webmail agent opened earlier in the run. Fake model, no browser.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402
from agents.submit import agent as submit  # noqa: E402

TASK = {"brief": "# Task\nBid for pumps (TX-0001-0042).\n\n## Submission\n\nEnter the bid in the portal."}
SITE = {"url": "https://portal.example/", "credentials": {"username": "u", "password": "p"}}
MAIL = {"url": "https://mail.example/", "credentials": {"username": "u", "password": "p"}}
ANSWER = {"tender_reference": "TX-0001-0042", "decision": "bid", "discount_percent": 0, "total_net": 0,
          "positions": []}


class FakeMailPage:
    async def goto(self, *_, **__):
        pass


class Stages(unittest.TestCase):
    def setUp(self):
        self.real = llm.investigate
        self.missions = {}

        async def investigate(tab, system, mission, schema, deadline, tag, **kwargs):
            self.missions[tag] = mission
            if tag == "submit":  # the agent requests a TAN and looks it up
                await kwargs["handlers"]["get_tan"]({"portal_message": "TAN sent"})
            return {"evidence": []}
        llm.investigate = investigate

    def tearDown(self):
        llm.investigate = self.real

    def test_the_first_stage_enters_nothing_of_the_bid(self):
        asyncio.run(submit.prepare(TASK, SimpleNamespace(site=SITE), "sales@own.example", time.time() + 60))
        mission = self.missions["submit-prepare"]
        self.assertIn("sales@own.example", mission)
        self.assertIn("never request a TAN and never submit", mission)

    def test_the_second_stage_continues_and_the_tan_look_up_knows_the_mailbox(self):
        visited = ["https://mail.example/?q=TX-0001-0042&page=2", "https://portal.example/tenders"]
        mail_tab = SimpleNamespace(site=MAIL, page=FakeMailPage())
        asyncio.run(submit.run(TASK, SimpleNamespace(site=SITE), mail_tab, ANSWER, [], {}, "sales@own.example",
                               time.time() + 600, "company data entered; stopped on the positions page", visited))
        self.assertIn("company data entered; stopped on the positions page", self.missions["submit"])
        self.assertIn("https://mail.example/?q=TX-0001-0042&page=2", self.missions["tan"])
        self.assertNotIn("portal.example", self.missions["tan"])  # another site's pages are no help in the mailbox

    def test_without_a_first_stage_or_mailbox_pages_the_missions_stay_as_they_were(self):
        mail_tab = SimpleNamespace(site=MAIL, page=FakeMailPage())
        asyncio.run(submit.run(TASK, SimpleNamespace(site=SITE), mail_tab, ANSWER, [], {}, "", time.time() + 600))
        self.assertNotIn("while the bid was calculated", self.missions["submit"])
        self.assertNotIn("Earlier in this run", self.missions["tan"])


if __name__ == "__main__":
    unittest.main()
