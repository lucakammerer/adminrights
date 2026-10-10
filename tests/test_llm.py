"""llm.investigate with a fake model: what a finish returns, and a tool that never answers.

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

    async def act(self, name, args):
        await asyncio.sleep(3600)  # a fetch that never answers


def finish(arguments: dict, tool: str = "finish"):
    call = SimpleNamespace(id="1", function=SimpleNamespace(name=tool, arguments=json.dumps(arguments)))
    message = SimpleNamespace(content=None, tool_calls=[call], model_dump=lambda **_: {"role": "assistant"})

    async def chat(*_, **__):
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])
    return chat


class InvestigateTest(unittest.TestCase):
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

    def test_a_hung_tool_ends_at_the_deadline_with_a_forced_finish(self):
        """run_1a7115a6522f64a1: a fetch hung until the stage cut and the tender agent's kept pages were lost."""
        llm.chat = finish({"url": "/document.zip"}, tool="fetch")
        result = asyncio.run(asyncio.wait_for(llm.investigate(Tab(), "", "", {}, time.time() + 2, "test"), 10))
        self.assertTrue(result["forced"])


if __name__ == "__main__":
    unittest.main()
