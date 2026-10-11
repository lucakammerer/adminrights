"""llm.chat with a fake client: a hung call gets a twin after HEDGE_AFTER and the first answer wins.

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


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)  # per call: seconds until it answers, None = never
        self.sent = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **_):
        self.sent += 1
        number, delay = self.sent, self.replies[self.sent - 1]
        await asyncio.sleep(3600 if delay is None else delay)
        return f"reply {number}"


class Chat(unittest.TestCase):
    def setUp(self):
        self.saved = llm._client, llm.HEDGE_AFTER
        llm.HEDGE_AFTER = 0.2

    def tearDown(self):
        llm._client, llm.HEDGE_AFTER = self.saved

    def ask(self, replies):
        llm._client = FakeClient(replies)
        started = time.time()
        reply = asyncio.run(llm.chat([]))
        return reply, time.time() - started, llm._client.sent

    def test_hung_call_is_overtaken_by_its_twin(self):
        reply, took, sent = self.ask([None, 0.05])
        self.assertEqual((reply, sent), ("reply 2", 2))
        self.assertLess(took, 1)

    def test_slow_call_still_wins_against_its_twin(self):
        reply, _, sent = self.ask([0.3, None])
        self.assertEqual((reply, sent), ("reply 1", 2))

    def test_quick_call_sends_no_twin(self):
        self.assertEqual(self.ask([0.01])[2], 1)


class Request(unittest.TestCase):
    """What a request carries: OpenRouter's provider routing on every call, the cache marker only where asked, and
    the caller's own options (thinking switched off) merged into the same body."""

    def setUp(self):
        self.saved = llm._client, llm.ROUTE, llm.CACHE, llm.OPENROUTER

    def tearDown(self):
        llm._client, llm.ROUTE, llm.CACHE, llm.OPENROUTER = self.saved

    def test_routing_cache_and_options_share_one_body(self):
        sent = []

        async def create(**kwargs):
            sent.append(kwargs)
            return "reply"
        llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        llm.ROUTE, llm.CACHE, llm.OPENROUTER = {"provider": {"sort": "latency"}}, {"cache_control": {"x": 1}}, True

        async def go():
            await llm.send([], None, 5, {}, cache=True)
            await llm.send([], None, 5, llm.reasoning("none"))
            await llm.send([], None, 5, llm.reasoning("low"))
        asyncio.run(go())
        self.assertEqual(sent[0]["extra_body"], {"provider": {"sort": "latency"}, "cache_control": {"x": 1}})
        self.assertEqual(sent[1]["extra_body"], {"provider": {"sort": "latency"}, "reasoning": {"enabled": False}})
        self.assertEqual((sent[2]["extra_body"], sent[2]["reasoning_effort"]), ({"provider": {"sort": "latency"}}, "low"))


if __name__ == "__main__":
    unittest.main()
