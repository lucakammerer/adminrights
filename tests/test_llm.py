"""llm.investigate with a fake model: what a finish call returns.

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


class Tab:
    async def read(self, offset=0):
        return "a page"


def finish(arguments: dict):
    call = SimpleNamespace(id="1", function=SimpleNamespace(name="finish", arguments=json.dumps(arguments)))
    message = SimpleNamespace(content=None, tool_calls=[call], model_dump=lambda **_: {"role": "assistant"})

    async def chat(*_, **__):
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])
    return chat


class FinishTest(unittest.TestCase):
    def setUp(self):
        self.chat, self.log = llm.chat, llm.log
        llm.log = lambda tag, text: None

    def tearDown(self):
        llm.chat, llm.log = self.chat, self.log

    def investigate(self, arguments):
        llm.chat = finish(arguments)
        return asyncio.run(llm.investigate(Tab(), "", "", {}, time.time() + 600, "test"))

    def test_finish_without_its_result_wrapper_keeps_the_fields(self):
        """Seen in run_4e7ea298c3d0b9bd: a found material was lost and two positions were omitted."""
        self.assertEqual(self.investigate({"material_number": "M"})["material_number"], "M")
        self.assertEqual(self.investigate({"result": {"material_number": "M"}})["material_number"], "M")


if __name__ == "__main__":
    unittest.main()
