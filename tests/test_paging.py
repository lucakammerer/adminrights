"""Model-selected pagination and the tool-loop reductions around it, using synthetic reader-format pages.

Run from the repo root: uv run --project agent --no-sync python -m unittest tests.test_paging -v
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
import paging  # noqa: E402

BASE = "https://site.example/list?folder=in&q=REF-1"


def listing(page: int, last: int, window: int = 3) -> str:
    pager = " ".join(f'[link "{number}" -> ?folder=in&q=REF-1&page={number}]'
                     for number in range(max(1, page - 1), min(last, page + window) + 1))
    rows = " ".join(f'[link "row {page}-{row}" -> /list?folder=in&q=REF-1&page={page}&message=m{page}{row}]'
                    for row in range(3))
    other = '[link "Archive" -> ?folder=archive&q=REF-1] [link "Sort" -> ?folder=in&q=REF-1&sort=date]'
    return f"Fetched {BASE}&page={page} (HTTP 200)\nResults page {page} of {last}\n{rows}\n{pager}\n{other}"


class Paging(unittest.TestCase):
    def test_only_one_numeric_list_component_is_a_page(self):
        self.assertEqual(paging.step(BASE, BASE + "&page=3"), (("query", "page"), 3))
        self.assertEqual(paging.step("https://s.example/qa/page/1", "https://s.example/qa/page/2"),
                         (("path", 3), 2))
        for other in (BASE.replace("folder=in", "folder=archive"), BASE + "&page=2&message=m1",
                      "https://other.example/list?folder=in&q=REF-1&page=2", BASE + "&sort=date"):
            self.assertIsNone(paging.step(BASE, other), other)

    def test_windowed_pager_is_followed_once_in_page_order(self):
        asked: list[str] = []

        async def fetch(url: str) -> str:
            asked.append(url)
            return listing(int(url.rsplit("page=", 1)[1]), 6)

        pages, note = asyncio.run(paging.rest(fetch, BASE + "&page=1", listing(1, 6)))
        self.assertEqual([url for url, _ in pages], [f"{BASE}&page={page}" for page in range(2, 7)])
        self.assertEqual(len(asked), 5)
        self.assertIn("5 further page", note)

    def test_long_list_is_bounded_and_explains_how_to_continue(self):
        async def fetch(url: str) -> str:
            return listing(int(url.rsplit("page=", 1)[1]), 20)

        pages, note = asyncio.run(paging.rest(fetch, BASE + "&page=1", listing(1, 20)))
        self.assertEqual(len(pages), paging.MAX_PAGES - 1)
        self.assertIn("more not read", note)


class Tab:
    def __init__(self):
        self.page = SimpleNamespace(url=BASE)
        self.acts: list[str] = []
        self.read_offsets: list[int] = []

    async def read(self, offset=0):
        self.read_offsets.append(offset)
        return "URL: " + BASE + "\nTitle: List\n\n" + listing(1, 3).split("\n", 1)[1]

    async def fetch(self, url):
        return listing(int(url.rsplit("page=", 1)[1]) if "page=" in url else 1, 3)

    async def act(self, name, args):
        self.acts.append(name)
        return await self.fetch(args["url"]) if name == "fetch" else await self.read()


def reply(*calls: tuple[str, dict]):
    tool_calls = [SimpleNamespace(id=str(index), function=SimpleNamespace(name=name, arguments=json.dumps(args)))
                  for index, (name, args) in enumerate(calls)]
    message = SimpleNamespace(content=None, tool_calls=tool_calls,
                              model_dump=lambda **_: {"role": "assistant", "content": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class Loop(unittest.TestCase):
    def setUp(self):
        self.real_chat = llm.chat
        self.tab = Tab()

    def tearDown(self):
        llm.chat = self.real_chat

    def run_turns(self, *turns) -> tuple[dict, list]:
        replies, seen = list(turns), []

        async def chat(messages, tools=None, **_):
            seen.append([dict(message) for message in messages if isinstance(message, dict)])
            return replies.pop(0)
        llm.chat = chat
        result = asyncio.run(llm.investigate(self.tab, "system", "mission", {"type": "object"}, time.time() + 300,
                                             "test"))
        return result, seen

    def test_fetch_all_pages_in_one_model_tool_call(self):
        _, seen = self.run_turns(reply(("fetch", {"url": BASE + "&page=1", "all_pages": True})),
                                 reply(("finish", {"result": {}})))
        output = seen[1][-1]["content"]
        for page in (1, 2, 3):
            self.assertIn(f"Results page {page} of 3", output)
        self.assertIn("Code read 2 further page", output)

    def test_read_all_pages_preserves_the_model_selected_offset(self):
        self.run_turns(reply(("read", {"offset": 50, "all_pages": True})), reply(("finish", {"result": {}})))
        self.assertEqual(self.tab.read_offsets, [0, 50])

    def test_keeping_a_page_already_read_does_not_repeat_its_contents(self):
        result, seen = self.run_turns(reply(("fetch", {"url": BASE + "&page=2"})),
                                      reply(("save_evidence", {"url": BASE + "&page=2", "label": "page 2"})),
                                      reply(("finish", {"result": {}})))
        self.assertEqual(len(result["evidence"]), 1)
        self.assertIn("Results page 2 of 3", result["evidence"][0])
        kept = [message["content"] for message in seen[2] if message.get("role") == "tool"][-1]
        self.assertTrue(kept.startswith(llm.KEPT_PREFIX + "1:"), kept)
        self.assertNotIn("Results page", kept)

    def test_last_evidence_and_finish_can_share_a_turn(self):
        result, seen = self.run_turns(reply(("save_evidence", {"url": BASE + "&page=2", "label": "page 2"}),
                                            ("finish", {"result": {"ok": True}})))
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(result["evidence"]), 1)
        self.assertTrue(result["ok"])
        self.assertNotIn("forced", result)

    def test_only_last_of_several_actions_repeats_the_page(self):
        _, seen = self.run_turns(reply(("fill", {"ref": 1, "text": "x"}), ("check", {"ref": 2}),
                                       ("click", {"ref": 3})), reply(("finish", {"result": {}})))
        outputs = [message["content"] for message in seen[1] if message.get("role") == "tool"]
        self.assertNotIn("Results page", outputs[0] + outputs[1])
        self.assertIn("Results page 1", outputs[2])
        self.assertEqual(self.tab.acts, ["fill", "check", "click"])


if __name__ == "__main__":
    unittest.main()
