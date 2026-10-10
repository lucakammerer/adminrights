"""The guards that keep a run going to a signed bid: model calls end on the wall clock even when the server trickles
bytes, a cut agent hands on the pages it kept, the requirements resolver gets a backup attempt, and a malformed
resolver answer or broken facts never end the run without an answer.

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

from openai import AsyncOpenAI  # noqa: E402

import agent  # noqa: E402
import llm  # noqa: E402

COMPLETION = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}]}).encode()


async def trickle(reader, writer, seconds=20):
    """A server that sends one keep-alive byte per second before its answer: the SDK's read timeout never fires."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n")
    try:
        for _ in range(seconds):
            await asyncio.sleep(1)
            writer.write(b"1\r\n \r\n")
            await writer.drain()
        writer.write(b"%x\r\n" % len(COMPLETION) + COMPLETION + b"\r\n0\r\n\r\n")
        await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


class HardCallBound(unittest.TestCase):
    def test_trickling_server_cannot_hold_a_call(self):
        async def scenario():
            server = await asyncio.start_server(trickle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            real = llm._client
            llm._client = AsyncOpenAI(base_url=f"http://127.0.0.1:{port}/v1", api_key="k", max_retries=0)
            began = time.time()
            try:
                with llm.limits(time.time() + 8, cap=2):
                    with self.assertRaises(TimeoutError):
                        await llm.chat([{"role": "user", "content": "x"}])
            finally:
                llm._client = real
                server.close()
            return time.time() - began
        self.assertLess(asyncio.run(scenario()), 10)  # the server would have answered after 20 s


class FakeTab:
    async def read(self, offset=0):
        return "a page"


def reply(name: str, args: dict):
    call = SimpleNamespace(id="1", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    message = SimpleNamespace(content=None, tool_calls=[call],
                              model_dump=lambda **_: {"role": "assistant", "content": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class CutKeepsEvidence(unittest.TestCase):
    def setUp(self):
        self.real_chat = llm.chat

    def tearDown(self):
        llm.chat = self.real_chat

    def test_cut_agent_hands_on_its_kept_pages(self):
        calls = []

        async def chat(messages, tools=None, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return reply("save_evidence", {"label": "approval"})
            await asyncio.sleep(100)  # stalls on its next model call

        llm.chat = chat

        async def scenario():
            job = llm.investigate(FakeTab(), "system", "mission", {"type": "object"}, time.time() + 300, "test")
            return await agent.safe("test", job, time.time() + 1)
        result = asyncio.run(scenario())
        self.assertTrue(result["forced"])
        self.assertEqual(result["evidence"], ["### approval\na page"])

    def test_job_without_evidence_keeps_its_fallback(self):
        async def scenario():
            return await agent.safe("test", asyncio.sleep(100), time.time() + 1, {"positions": []})
        self.assertEqual(asyncio.run(scenario()), {"positions": []})


class Requirements(unittest.TestCase):
    def setUp(self):
        self.real = agent.resolvers.requirements, agent.BACKUP_AFTER
        agent.BACKUP_AFTER = 0.2

    def tearDown(self):
        agent.resolvers.requirements, agent.BACKUP_AFTER = self.real

    def run_with(self, medium, low, seconds=2):
        async def requirements(*_, effort="medium"):
            return await (medium() if effort == "medium" else low())
        agent.resolvers.requirements = requirements
        return asyncio.run(agent.resolve_requirements((), time.time() + seconds))

    def test_backup_counts_when_the_first_attempt_hangs(self):
        async def hangs():
            await asyncio.sleep(100)

        async def answers():
            return {"positions": [{"position": "1"}]}
        self.assertEqual(self.run_with(hangs, answers), [{"position": "1"}])

    def test_fast_first_attempt_starts_no_backup(self):
        started = []

        async def answers():
            return {"positions": [{"position": "1"}]}

        async def backup():
            started.append(1)
            return {"positions": [{"position": "2"}]}
        self.assertEqual(self.run_with(answers, backup), [{"position": "1"}])
        self.assertEqual(started, [])

    def test_malformed_answers_give_no_positions(self):
        self.assertEqual(agent.positions({"result": []}), [])
        self.assertEqual(agent.positions({"positions": "none"}), [])
        self.assertEqual(agent.positions({"positions": [{"bore_mm": 50}, "x", {"position": 2}]}),
                         [{"position": "2"}])


class Bid(unittest.TestCase):
    TENDER = {"tender_reference": "REF"}
    COMMERCIALS = {"tender_reference": "REF", "positions": []}

    def test_broken_erp_finding_omits_only_its_position(self):
        requirements = {"positions": [{"position": "1", "final_quantity_pieces": 2},
                                      {"position": "2", "final_quantity_pieces": "no number"}]}
        erp = {"1": {"material_number": "M", "price_condition": {"scales": [{"price": "1"}]}}}  # no from_quantity
        result = agent.bid(self.TENDER, requirements, self.COMMERCIALS, erp)
        self.assertEqual(result["answer"]["decision"], "bid")
        self.assertEqual(result["answer"]["tender_reference"], "REF")
        self.assertEqual(sorted(result["omitted"]), ["1", "2"])

    def test_broken_commercials_still_give_an_answer(self):
        requirements = {"positions": [{"position": "1", "final_quantity_pieces": 2}]}
        commercials = {"positions": [{"no position key": True}]}
        result = agent.bid(self.TENDER, requirements, commercials, {})
        self.assertEqual(result["answer"]["decision"], "bid")
        self.assertEqual(result["answer"]["tender_reference"], "REF")
        self.assertEqual(result["omitted"], ["1"])


if __name__ == "__main__":
    unittest.main()
