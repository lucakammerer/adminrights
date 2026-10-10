"""Stress level S3 (I24, rules 3, 8, 9): the matching material of one position shows as blocked, so the bid must be
no_bid. Controls: the unchanged ERP bids with the expected material, and a search starved of time never reports a
no-match (it is omitted instead).

The ERP's responses are rewritten in this tool's own browser (context.route), never in agent/: in every response that
names the target material, its status is turned from released to blocked in the row or page that belongs to it
(list row, detail page, tooltip, status code). The target is read from eval/public-1/gather-facts.json at run time.
Requirements and the other positions' ERP results come from a run_agents.py fixture (requirements.json, erp.json):
each stage logs in and searches only the requirement whose material is shown blocked, then calc decides the bid over
all positions. Stages run two at a time, so S3 stays within the team's shared model capacity.

Run from the repo root, proxy running, `source tools/dev-env.sh`, `atira status` checked:
    HEADLESS=1 uv run --project agent --no-sync python tools/stress/s3_nobid.py FIXTURE_DIR [--position P] \
        [--attempts 3] [--controls] [--deadline 300]
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

import calc  # noqa: E402
import llm  # noqa: E402
import run as contract  # noqa: E402
from agents.erp import agent as erp_agent  # noqa: E402
from agents.resolvers import agent as resolvers  # noqa: E402
from browser import Tab  # noqa: E402

SPEC_KEYS = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification", "catalogue_group")
# How the scouting ERP shows a material's status (tool-side knowledge of the public site, never in agent/): a field
# labelled status holding a code (01 released, 03 blocked) or a word. The status-key legend and stock notes that
# merely mention "released"/"blocked" are left alone.
STATUS_LABEL = re.compile(r'(aria-label="[^"]*[Ss]tatus[^"]*:\s*)01(?=")')
STATUS_FIELD = re.compile(r'(<(output|span|td|dd)\b[^>]*[Ss]tatus[^>]*>\s*)(01|freigegeben|released|active|aktiv)(?=\s*<)')
BLOCKED = {"01": "03", "freigegeben": "gesperrt", "released": "blocked", "active": "blocked", "aktiv": "gesperrt"}


def block_status(text: str) -> str:
    text = STATUS_LABEL.sub(lambda m: m.group(1) + "03", text)
    return STATUS_FIELD.sub(lambda m: m.group(1) + BLOCKED[m.group(3)], text)


def rewrite(body: str, material: str, url: str) -> str:
    """Mark `material` blocked on the pages about it (its URL names it); list rows show no status on this site."""
    return block_status(body) if material and material in url else body


async def erp_stage(task, entry, requirement, seconds, material=None):
    """ERP login + the search for one requirement, in a fresh browser; `material` is shown blocked if given."""
    rewritten = [0]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=os.environ.get("HEADLESS") == "1")
        context = await browser.new_context()

        async def route(r):
            try:
                response = await r.fetch()
            except Exception:  # noqa: BLE001  a slow site: fail the request (the agent retries), never pass it unrewritten
                return await r.abort()
            ctype = response.headers.get("content-type", "")
            if not any(t in ctype for t in ("html", "json", "text")):
                return await r.fulfill(response=response)
            body = await response.text()
            new = rewrite(body, material, r.request.url)
            rewritten[0] += new != body
            await r.fulfill(response=response, body=new)

        if material:
            await context.route("**/*", route)
        page = await context.new_page()
        await page.goto(entry["url"], wait_until="domcontentloaded")
        tab = Tab(page, entry)
        await erp_agent.login(task, tab, time.time() + 120)
        result = await erp_agent.run(task, tab, requirement, time.time() + seconds - 30)  # the search's own time
        if result.get("forced"):  # as agent.main: a search cut at its deadline proves nothing
            result.pop("no_match", None)
        await browser.close()
    return result, rewritten[0]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--position", help="position whose material is shown blocked (default: the first)")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--deadline", type=float, default=300)
    args = parser.parse_args()
    task, _ = contract.load_run()
    facts = json.loads((ROOT / "eval/public-1/gather-facts.json").read_text())
    requirements = json.loads((args.fixture / "requirements.json").read_text())
    tender = json.loads((args.fixture / "tender_portal.json").read_text())["result"]
    commercials = json.loads((args.fixture / "commercials.json").read_text()) \
        if (args.fixture / "commercials.json").exists() else {}
    roles = await resolvers.sites(task)
    position = args.position or next(iter(facts["erp"]))  # the expected material of this position is shown blocked
    material = facts["erp"][position]
    runs = [("blocked", material, args.deadline)] * args.attempts
    if args.controls:
        runs += [("unchanged", None, args.deadline), ("starved", None, 20)]
    previous = json.loads((args.fixture / "erp.json").read_text())
    target = next(r for r in requirements["positions"] if str(r.get("position")) == position)
    key = tuple(str(target.get(k)) for k in SPEC_KEYS)
    requirement = {k: target.get(k) for k in SPEC_KEYS}
    gate = asyncio.Semaphore(2)

    async def stage(name, blocked, seconds):
        async with gate:
            result, rewritten = await erp_stage(task, roles["erp"], requirement, seconds, blocked)
        erp = {}
        for r in requirements["positions"]:
            same = tuple(str(r.get(k)) for k in SPEC_KEYS) == key
            erp[r["position"]] = result if same else previous.get(json.dumps(tuple(str(r.get(k)) for k in SPEC_KEYS)), {})
        answer = calc.compute(calc.facts(tender, requirements, commercials, erp))["answer"]
        if name == "blocked":
            ok = answer["decision"] == "no_bid"
        elif name == "unchanged":
            ok = answer["decision"] == "bid" and result.get("material_number") == material
        else:
            ok = answer["decision"] != "no_bid"  # starved: an unfinished search is omitted, never a no_bid
        llm.log("s3", f"{name}: decision {answer['decision']}, found {result.get('material_number')!r}, "
                      f"no_match {bool(result.get('no_match'))}, responses rewritten {rewritten}: {'PASS' if ok else 'FAIL'}")
        return {"run": name, "decision": answer["decision"], "found": result.get("material_number"),
                "no_match": bool(result.get("no_match")), "candidates": result.get("candidates"),
                "rewritten": rewritten, "ok": ok}

    rows = await asyncio.gather(*(stage(*run) for run in runs))
    out = args.fixture / f"s3-{time.strftime('%H%M%S')}.json"
    out.write_text(json.dumps(rows, indent=1))
    passed = sum(r["ok"] for r in rows)
    print(f"S3 no-bid: {passed}/{len(rows)} passed ({out})")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
