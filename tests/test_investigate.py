"""llm.investigate with a fake model: a finish sent after the time warning is marked forced, so a search the agent
never completed can't count as no_match (I1); a finish without its wrapper and a tool that never answers.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import llm  # noqa: E402


class FakeTab:
    async def read(self, offset=0):
        return "a page"

    async def act(self, name, args):
        await asyncio.sleep(3600)  # a fetch that never answers


def finish(result: dict, arguments: dict | None = None, tool: str = "finish"):
    """A model reply that calls finish(result), or `tool` with `arguments` as sent."""
    arguments = {"result": result} if arguments is None else arguments
    call = SimpleNamespace(id="1", function=SimpleNamespace(name=tool, arguments=json.dumps(arguments)))
    message = SimpleNamespace(content=None, tool_calls=[call],
                              model_dump=lambda **_: {"role": "assistant", "content": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class Investigate(unittest.TestCase):
    def setUp(self):
        self.real_chat = llm.chat
        self.prompts = []

        async def chat(messages, tools=None, **kwargs):
            self.prompts.append([m.get("content") for m in messages if isinstance(m, dict)])
            return finish({"material_number": "", "no_match": True, "why": "time ran out"})
        llm.chat = chat

    def tearDown(self):
        llm.chat = self.real_chat

    def run_agent(self, seconds_left: float, **kwargs) -> dict:
        return asyncio.run(llm.investigate(FakeTab(), "system", "mission", {"type": "object"},
                                           time.time() + seconds_left, "test", **kwargs))

    def test_finish_in_time_is_not_forced(self):
        result = self.run_agent(300)
        self.assertTrue(result["no_match"])
        self.assertNotIn("forced", result)

    def test_finish_after_the_warning_is_forced(self):
        result = self.run_agent(50)  # inside warn_at (60 s): the warning goes out before the first step
        self.assertIn(llm.FINISH_NOW, self.prompts[0])
        self.assertTrue(result["forced"])

    def test_custom_warning_counts_too(self):
        result = self.run_agent(150, warn_at=180, warning="sign now")
        self.assertIn("sign now", self.prompts[0])
        self.assertTrue(result["forced"])

    def test_finish_without_its_result_wrapper_keeps_the_fields(self):
        """run_4e7ea298c3d0b9bd: a found material was lost and two positions were omitted."""
        async def chat(*_, **__):
            return finish({}, {"material_number": "M"})
        llm.chat = chat
        self.assertEqual(self.run_agent(300)["material_number"], "M")

    def test_a_hung_tool_ends_at_the_deadline_with_a_forced_finish(self):
        """run_1a7115a6522f64a1: a fetch hung until the stage cut and the tender agent's kept pages were lost."""
        async def chat(*_, **__):
            return finish({}, {"url": "/document.zip"}, tool="fetch")
        llm.chat = chat
        result = asyncio.run(asyncio.wait_for(llm.investigate(FakeTab(), "", "", {}, time.time() + 2, "test",
                                                              warn_at=0), 10))
        self.assertTrue(result["forced"])

    def test_reopening_a_kept_page_says_it_is_kept(self):
        """run_0a26a180075ecc2c: an ERP search reopened kept pages 14 times to re-check values, then hit its step limit."""
        class Tab(FakeTab):
            page = SimpleNamespace(url="https://erp.example/start")

            async def fetch(self, url):
                self.fetched = getattr(self, "fetched", 0) + 1
                return f"Fetched {url} (HTTP 200)\nrecord" + (" changed" if self.fetched == 4 else "")

            async def act(self, name, args):
                return await self.fetch(args["url"])
        replies = iter([finish({}, {"url": "/record?id=1", "label": "record"}, tool="save_evidence"),
                        finish({}, {"url": "https://erp.example/record?id=1"}, tool="fetch"),
                        finish({}, {"url": "/record?id=2"}, tool="fetch"),
                        finish({}, {"url": "/record?id=1"}, tool="fetch"),  # its content changed since it was kept
                        finish({"material_number": "M"})])

        async def chat(messages, *_, **__):
            self.prompts.append([m.get("content") for m in messages if isinstance(m, dict)])
            return next(replies)
        llm.chat = chat
        asyncio.run(llm.investigate(Tab(), "", "", {}, time.time() + 300, "test"))
        self.assertIn("Unchanged since you kept it as evidence #1", self.prompts[2][-1])
        self.assertNotIn("Unchanged since", self.prompts[3][-1])
        self.assertNotIn("Unchanged since", self.prompts[4][-1])


if __name__ == "__main__":
    unittest.main()
