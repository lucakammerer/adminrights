"""Mutation tests (I20, rule 19): recorded pages rewritten the way another site would show the same facts
(tools/stress/mutations.js: synonym labels, hidden decoys, shuffled menus and table rows, swapped number formats,
content moved into an extra frame, invisible characters inside identifiers, dates shown as weekday and time; with widgets, tables as styled span rows and links as scripted elements) must give
the reader the same facts, a ref for every scripted link and none of the decoys. No website and no model: headless Chromium, network blocked.

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
    """Identifiers and numbers in the reader's text, number formats normalised (separators dropped), dates as
    yyyymmdd whether written dd.mm.yyyy or ISO."""
    text = re.sub(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", r"\3\2\1", text)
    text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})(?=\b|T)", r"\1\2\3", text)
    ids = set(re.findall(r"\b[A-Z]{1,5}-\d[\d-]*\b", text))
    numbers = {re.sub(r"[.,]", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", text) if len(re.sub(r"\D", "", n)) >= 2}
    return ids | numbers


async def read_all(seeds: list) -> dict:
    """seeds: None (unmutated), a seed, or (seed, "widgets") for the framework-app markup as well."""
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.route("**/*", lambda route: route.abort())  # recorded pages only: nothing leaves the test
        page = await context.new_page()
        for path in PAGES:
            for seed in seeds:
                await page.set_content(path.read_text(errors="ignore"), wait_until="domcontentloaded")
                number, widgets = seed if isinstance(seed, tuple) else (seed, False)
                stats = await page.evaluate(MUTATIONS, {"seed": number, "widgets": bool(widgets)}) if seed else {}
                await page.wait_for_function("[...document.querySelectorAll('iframe')].every(f => f.contentDocument &&"
                                             " f.contentDocument.readyState === 'complete')")  # the extra frame loaded
                out[(path.name, seed)] = ((await page.evaluate(f"({READER})({{}})"))["text"], stats)
        await browser.close()
    return out


@unittest.skipUnless(PAGES, "no recorded pages in eval/fixtures/pages")
class MutatedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seeds = [3, 11, (3, "widgets")]
        cls.read = asyncio.run(read_all([None] + cls.seeds))

    def test_facts_survive_and_decoys_stay_out(self):
        self.assertGreater(sum(stats.get("invisible", 0) for _, stats in self.read.values()), 0)
        self.assertGreater(sum(stats.get("dates", 0) for _, stats in self.read.values()), 0)
        for path in PAGES:
            plain = facts(self.read[(path.name, None)][0])
            self.assertTrue(plain, path.name)
            for seed in self.seeds:
                text, stats = self.read[(path.name, seed)]
                if isinstance(seed, tuple):  # a scripted link has no href: compare the page text without link targets
                    plain = facts(re.sub(r" -> [^\]]*\]", "]", self.read[(path.name, None)][0]))
                with self.subTest(page=path.name, seed=seed):
                    self.assertGreater(stats["decoys"], 0)
                    # a decoy in its background's colour may be kept, but only inside the reader's mark
                    self.assertNotIn("S2DECOY", re.sub(r"\(text in its background's colour: [^)]*S2DECOY\)", "", text))
                    self.assertEqual(plain - facts(text), set())
                    links = self.read[(path.name, None)][0].count(':link "')
                    self.assertEqual(text.count(':link "') + text.count(":clickable]"), links)  # every link still usable


if __name__ == "__main__":
    unittest.main()
