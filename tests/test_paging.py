"""paging: code follows the page links of a list the model chose (all_pages), on synthetic pages in reader.js's
link format; and the model loop around it: a page the model read is kept without being shown again, of several
actions in one turn only the last one shows the page, and finish in the turn of the last save_evidence keeps it.

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
import paging  # noqa: E402

BASE = "https://site.example/list?folder=in&q=REF-1"


def listing(n: int, last: int, window: int = 3) -> str:
    """Page n of a list of `last` pages whose pager links at most `window` pages after it, plus row links."""
    pager = " ".join(f'[link "{k}" -> ?folder=in&q=REF-1&page={k}]'
                     for k in range(max(1, n - 1), min(last, n + window) + 1))
    rows = " ".join(f'[link "row {n}-{r}" -> /list?folder=in&q=REF-1&page={n}&message=m{n}{r}]' for r in range(3))
    folders = '[link "Archive" -> ?folder=archive&q=REF-1] [link "Sort" -> ?folder=in&q=REF-1&sort=date]'
    return f"Fetched {BASE}&page={n} (HTTP 200)\nResults page {n} of {last}\n{rows}\n{pager}\n{folders}"


class Step(unittest.TestCase):
    def test_a_page_number_in_the_query(self):
        self.assertEqual(paging.step(BASE, BASE + "&page=3"), (("query", "page"), 3))

    def test_a_page_number_in_the_path(self):
        self.assertEqual(paging.step("https://s.example/qa/page/1", "https://s.example/qa/page/2"), (("path", 3), 2))

    def test_other_links_are_no_pages(self):
        for other in (BASE.replace("folder=in", "folder=archive"), BASE + "&page=2&message=m1",
                      "https://other.example/list?folder=in&q=REF-1&page=2", "https://site.example/item/7",
                      BASE + "&sort=date"):
            self.assertIsNone(paging.step(BASE, other), other)

    def test_body_ignores_headers_and_refs(self):
        live = "URL: https://s.example/a\nTitle: A\n\nRow 1 [12:link \"x\" -> /x]"
        fetched = "Fetched https://s.example/a (HTTP 200)\nRow 1 [link \"x\" -> /x]"
        self.assertEqual(paging.body(live), paging.body(fetched))


class Rest(unittest.TestCase):
    def collect(self, last: int, start: int = 1) -> tuple[list[str], str, list[str]]:
        asked: list[str] = []

        async def fetch(url: str) -> str:
            asked.append(url)
            return listing(int(url.rsplit("page=", 1)[1]), last)
        pages, note = asyncio.run(paging.rest(fetch, f"{BASE}&page={start}", listing(start, last)))
        return [u for u, _ in pages], note, asked

    def test_every_page_of_a_windowed_pager_once_in_order(self):
        urls, note, asked = self.collect(6)
        self.assertEqual(urls, [f"{BASE}&page={k}" for k in range(2, 7)])
        self.assertEqual(len(asked), 5)
        self.assertIn("5 further page", note)

    def test_from_a_middle_page_the_earlier_pages_too(self):
        urls, _, _ = self.collect(4, start=3)
        self.assertEqual(urls, [f"{BASE}&page={k}" for k in (1, 2, 4)])

    def test_a_long_list_stops_and_says_what_is_left(self):
        urls, note, _ = self.collect(20)
        self.assertEqual(len(urls), paging.MAX_PAGES - 1)
        self.assertIn("more not read", note)

    def test_rows_linked_by_id_are_no_pager(self):
        rows = " ".join(f'[link "Order confirmation {i}" -> ?folder=in&id={i}]' for i in (17, 18, 23, 42))
        ids = " ".join(f'[link "{i}" -> ?folder=in&id={i}]' for i in (17, 18, 23, 42))
        for text in (rows, ids):
            pages, note = asyncio.run(paging.rest(None, "https://s.example/inbox?folder=in", text))
            self.assertEqual(pages, [], text)

    def test_a_next_link_alone_is_a_pager(self):
        async def fetch(url: str) -> str:
            return "Fetched x (HTTP 200)\nsecond page"
        text = '[link "Order confirmation 7" -> ?folder=in&id=7] [link "Next" -> ?folder=in&page=2]'
        pages, _ = asyncio.run(paging.rest(fetch, "https://s.example/inbox?folder=in", text))
        self.assertEqual([u for u, _ in pages], ["https://s.example/inbox?folder=in&page=2"])

    def test_a_page_without_pager(self):
        pages, note = asyncio.run(paging.rest(None, BASE, "Fetched x (HTTP 200)\nOne result [link \"a\" -> /a/1]"))
        self.assertEqual(pages, [])
        self.assertIn("No links to further pages", note)


class Tab:
    """A fake tab: the current page is page 1 of a 3-page list; fetch serves any page of it."""
    def __init__(self):
        self.page = SimpleNamespace(url=BASE)
        self.acts: list[str] = []

    async def read(self, offset=0):
        return "URL: " + BASE + "\nTitle: List\n\n" + listing(1, 3).split("\n", 1)[1]

    async def fetch(self, url):
        return listing(int(url.rsplit("page=", 1)[1]) if "page=" in url else 1, 3)

    async def act(self, name, args):
        self.acts.append(name)
        return await self.fetch(args["url"]) if name == "fetch" else await self.read()


def reply(*calls: tuple[str, dict]):
    tool_calls = [SimpleNamespace(id=str(i), function=SimpleNamespace(name=name, arguments=json.dumps(args)))
                  for i, (name, args) in enumerate(calls)]
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

        async def chat(messages, tools=None, **kwargs):
            seen.append([dict(m) for m in messages if isinstance(m, dict)])
            return replies.pop(0)
        llm.chat = chat
        result = asyncio.run(llm.investigate(self.tab, "system", "mission", {"type": "object"}, time.time() + 300,
                                             "test"))
        return result, seen

    def test_fetch_all_pages_in_one_call(self):
        _, seen = self.run_turns(reply(("fetch", {"url": BASE + "&page=1", "all_pages": True})),
                                 reply(("finish", {"result": {}})))
        output = seen[1][-1]["content"]
        for k in (1, 2, 3):
            self.assertIn(f"Results page {k} of 3", output)
        self.assertIn("Code read 2 further page", output)

    def test_keeping_a_page_read_before_does_not_show_it_again(self):
        result, seen = self.run_turns(reply(("fetch", {"url": BASE + "&page=2"})),
                                      reply(("save_evidence", {"url": BASE + "&page=2", "label": "page 2"})),
                                      reply(("finish", {"result": {}})))
        self.assertEqual(len(result["evidence"]), 1)
        self.assertIn("Results page 2 of 3", result["evidence"][0])
        kept = [m["content"] for m in seen[2] if m.get("role") == "tool"][-1]
        self.assertTrue(kept.startswith(llm.KEPT_PREFIX + "1:"), kept)
        self.assertNotIn("Results page", kept)

    def test_finish_in_the_turn_of_the_last_save_evidence(self):
        result, seen = self.run_turns(reply(("save_evidence", {"url": BASE + "&page=2", "label": "page 2"}),
                                            ("finish", {"result": {"ok": True}})))
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(result["evidence"]), 1)
        self.assertTrue(result["ok"])
        self.assertNotIn("forced", result)

    def test_keep_all_pages(self):
        result, _ = self.run_turns(reply(("save_evidence", {"url": BASE + "&page=1", "label": "list",
                                                            "all_pages": True})),
                                   reply(("finish", {"result": {}})))
        self.assertEqual(len(result["evidence"]), 3)

    def test_of_several_actions_only_the_last_shows_the_page(self):
        _, seen = self.run_turns(reply(("fill", {"ref": 1, "text": "x"}), ("check", {"ref": 2}),
                                       ("click", {"ref": 3})),
                                 reply(("finish", {"result": {}})))
        outputs = [m["content"] for m in seen[1] if m.get("role") == "tool"]
        self.assertEqual(len(outputs), 3)
        self.assertNotIn("Results page", outputs[0] + outputs[1])
        self.assertIn("Results page 1", outputs[2])
        self.assertEqual(self.tab.acts, ["fill", "check", "click"])


if __name__ == "__main__":
    unittest.main()
