"""llm.investigate with a fake model: a finish sent after the time warning is marked forced, so a search the agent
never completed can't count as no_match (I1).

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


def finish(result: dict):
    """A model reply that calls finish(result)."""
    call = SimpleNamespace(id="1", function=SimpleNamespace(name="finish", arguments=json.dumps({"result": result})))
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


if __name__ == "__main__":
    unittest.main()
