"""llm.investigate with a fake model: a finish sent after the time warning is marked forced, so a search the agent
never completed can't count as no_match (I1); a finish without its wrapper and a tool that never answers; a history
the prompt cache can serve (it only grows until COMPACT_AT, no page twice in one turn, the cache only where it is read).

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
from agents.common import evidence  # noqa: E402


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


class PageTab:
    """A tab whose every read is a new long page; an action returns the page after it, as Tab.act does."""

    def __init__(self):
        self.reads = 0

    async def read(self, offset=0):
        self.reads += 1
        return f"page {self.reads}\n" + "x" * 20_000

    async def act(self, name, args):
        return await self.read()


def turn(*calls):
    """A model reply that calls each (tool, arguments) in one turn."""
    tool_calls = [SimpleNamespace(id=str(i), function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
                  for i, (name, arguments) in enumerate(calls)]
    message = SimpleNamespace(content=None, tool_calls=tool_calls,
                              model_dump=lambda **_: {"role": "assistant", "content": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class History(unittest.TestCase):
    """2026-10-10: shortening older reads on every step left a third of a Haiku run's prompt to the cache."""

    def setUp(self):
        self.real = llm.chat, llm.COMPACT_AT, llm.CACHE

    def tearDown(self):
        llm.chat, llm.COMPACT_AT, llm.CACHE = self.real

    def play(self, turns, tab=None):
        """Plays `turns`, then finish: every prompt as sent (its messages as JSON) and the options of every call."""
        sent, options = [], []

        async def chat(messages, tools=None, **kwargs):
            sent.append([json.dumps(m, sort_keys=True) for m in messages])
            options.append(kwargs)
            return turns[len(sent) - 1] if len(sent) <= len(turns) else finish({})
        llm.chat = chat
        self.result = asyncio.run(llm.investigate(tab or PageTab(), "system", "mission", {"type": "object"},
                                                  time.time() + 300, "test"))
        return sent, options

    @staticmethod
    def rewrites(sent) -> int:
        """Calls whose prompt changed what the call before them sent (the cache serves only an unchanged start)."""
        return sum(1 for before, after in zip(sent, sent[1:]) if after[:len(before)] != before)

    @staticmethod
    def results(prompt) -> list[str]:
        return [m["content"] for m in map(json.loads, prompt) if m["role"] == "tool"]

    def test_history_only_grows_below_the_cap(self):
        llm.COMPACT_AT = 1_000_000  # never reached
        sent, _ = self.play([turn(("read", {}))] * 10)
        self.assertEqual(self.rewrites(sent), 0)  # shortening one step per call rewrote 6 of these prompts
        self.assertFalse(any("shortened" in r for r in self.results(sent[-1])))

    def test_past_the_cap_older_reads_shrink_at_once(self):
        llm.COMPACT_AT = 70_000  # tokens: about ten steps of 20,000 characters
        sent, _ = self.play([turn(("read", {}))] * 12)
        self.assertEqual(self.rewrites(sent), 1)  # shortening one step per call rewrote 8 of these prompts
        results = self.results(sent[-1])
        self.assertIn("shortened", results[0])
        self.assertTrue(all(len(r) > 20_000 for r in results[-llm.KEEP_STEPS:]))

    def test_a_read_in_the_turn_of_an_action_adds_no_second_copy(self):
        tab = PageTab()
        sent, _ = self.play([turn(("click", {"ref": 1}), ("read", {}), ("read", {"offset": 14_000}))], tab)
        click, read, further = self.results(sent[-1])
        self.assertTrue(click.startswith("page 2"))
        self.assertEqual(read, llm.SHOWN.format("click"))
        self.assertTrue(further.startswith("page 3"))  # an offset still reads: it continues a long page
        self.assertEqual(tab.reads, 3)

    def test_a_read_in_a_later_turn_reads_again(self):
        tab = PageTab()
        self.play([turn(("click", {"ref": 1})), turn(("read", {}))], tab)
        self.assertEqual(tab.reads, 3)

    def test_only_the_tool_loop_asks_for_the_cache(self):
        _, options = self.play([turn(("read", {}))])
        self.assertTrue(all(o.get("cache") is True for o in options))
        asked = []

        async def chat(messages, tools=None, **kwargs):
            asked.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
        llm.chat = chat
        asyncio.run(llm.ask_json("system", "question", effort="low"))
        self.assertFalse(asked[0].get("cache"))
        self.assertEqual(asked[0]["reasoning_effort"], "low")

    def test_pages_kept_in_the_turn_of_finish_count_and_a_list_comes_whole(self):
        class ListTab(PageTab):
            page = SimpleNamespace(url="https://site.example/start")

            async def fetch(self, url):
                return f"Fetched {url} (HTTP 200)\nmessage at {url}"

            async def fetch_list(self, url):
                return [(url, f"Fetched {url} (HTTP 200)\nrow 1"), (url + "&page=2", "Fetched x (HTTP 200)\nrow 2")], \
                    "[this list: 2 pages read]"
        self.play([turn(("save_evidence", {"url": "/messages/1", "label": "approval"}),
                        ("save_evidence", {"url": "/list?q=x", "label": "results", "all_pages": True}),
                        ("finish", {"result": {"kept": "approval, results"}}))], ListTab())
        result = self.result
        self.assertEqual(result["kept"], "approval, results")
        self.assertEqual([page.split("\n")[0] for page in result["evidence"]],
                         ["### approval", "### results", "### results (page 2)"])
        self.assertEqual(result["visited"], ["https://site.example/messages/1", "https://site.example/list?q=x"])
        self.assertNotIn("site.example", evidence(result).split("Pages kept as evidence:")[0])  # no URL list for the analyst


if __name__ == "__main__":
    unittest.main()
