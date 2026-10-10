"""Mutation tests (I20, rule 19): recorded pages rewritten the way another site would show the same facts
(tools/stress/mutations.js: synonym labels, hidden decoys, shuffled menus, swapped number formats) must give the
reader the same facts and none of the decoys. No website and no model: headless Chromium, network blocked.

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import asyncio
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

from browser import READER  # noqa: E402

PAGES = sorted((ROOT / "eval/fixtures/pages").glob("*.html"))
MUTATIONS = (ROOT / "tools/stress/mutations.js").read_text()


def facts(text: str) -> set[str]:
    """Identifiers and numbers in the reader's text, number formats normalised (separators dropped)."""
    ids = set(re.findall(r"\b[A-Z]{1,5}-\d[\d-]*\b", text))
    numbers = {re.sub(r"[.,]", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", text) if len(re.sub(r"\D", "", n)) >= 2}
    return ids | numbers


async def read_all(seeds: list[int | None]) -> dict:
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.route("**/*", lambda route: route.abort())  # recorded pages only: nothing leaves the test
        page = await context.new_page()
        for path in PAGES:
            for seed in seeds:
                await page.set_content(path.read_text(errors="ignore"), wait_until="domcontentloaded")
                stats = await page.evaluate(f"({MUTATIONS})({{seed: {seed}}})") if seed else {}
                out[(path.name, seed)] = ((await page.evaluate(f"({READER})({{}})"))["text"], stats)
        await browser.close()
    return out


@unittest.skipUnless(PAGES, "no recorded pages in eval/fixtures/pages")
class MutatedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seeds = [3, 11]
        cls.read = asyncio.run(read_all([None] + cls.seeds))

    def test_facts_survive_and_decoys_stay_out(self):
        for path in PAGES:
            plain = facts(self.read[(path.name, None)][0])
            self.assertTrue(plain, path.name)
            for seed in self.seeds:
                text, stats = self.read[(path.name, seed)]
                with self.subTest(page=path.name, seed=seed):
                    self.assertGreater(stats["decoys"], 0)
                    self.assertNotIn("S2DECOY", text)
                    self.assertEqual(plain - facts(text), set())


if __name__ == "__main__":
    unittest.main()
