"""Single-agent runner and recorder (T4.3): run any subset of the gathering agents against the scouting sites, each in
a browser of its own, and save a fixture: every agent's result and kept evidence, the raw HTML of every page it read
or fetched, and a step summary. With --resolve the two resolvers run on the result and a gather score compares their
facts with eval/public-1/gather-facts.json. Dev tool: it launches its own Chromium, so it lives outside agent/.

Run from the repo root, with `atira models proxy` running and `source tools/dev-env.sh` done:
    HEADLESS=1 uv run --project agent --no-sync python tools/stress/run_agents.py \
        [--agents tender_portal,supplier_portal,webmail,erp] [--deadline 540] [--out DIR] [--resolve] \
        [--requirements FILE] [--from DIR]

--mutate SEED runs stress level S2: every read-only page (GET, no password field, no POST form) is rewritten by
tools/stress/mutations.js before the agent sees it (synonym labels, hidden decoys, shuffled menus, swapped number
formats with their hints, shuffled table rows, main content in an extra frame), in this tool's browser only. Pass:
the gather score stays what it is unmutated.
--s4 PAGE runs stress level S4 (needs --resolve): the mail message recorded in PAGE (raw HTML from a fixture, its
URL in that fixture's index.json) disappears from the mailbox (its list rows go, its pages answer 404) and appears
as an attachment page linked from every tender-portal page. After the resolvers, agents.sweep looks for the open
facts on the open tabs and the resolver runs again with the swept pages. Pass: the moved fact is resolved.
--requirements FILE (a requirements.json of an earlier fixture) runs one ERP agent per distinct requirement after the
ERP login. --from DIR reuses the agent results of an earlier fixture for agents not run now (e.g. --resolve only).
Check `atira status` first: nothing runs while a scored submission runs.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))

from playwright.async_api import async_playwright  # noqa: E402

import agent as orchestration  # noqa: E402
import llm  # noqa: E402
import run as contract  # noqa: E402
from agents.erp import agent as erp_agent  # noqa: E402
from agents.resolvers import agent as resolvers  # noqa: E402
from agents.supplier_portal import agent as supplier_portal  # noqa: E402
from agents.tender_portal import agent as tender_portal  # noqa: E402
from agents.sweep import agent as sweep_agent  # noqa: E402
from agents.webmail import agent as webmail  # noqa: E402
from browser import Tab  # noqa: E402

AGENTS = ("tender_portal", "supplier_portal", "webmail", "erp")
TAGS = {"tender_portal": "tender-portal", "supplier_portal": "supplier-portal", "webmail": "webmail", "erp": "erp-login"}
SPEC_KEYS = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification", "catalogue_group")
EVENTS: list[tuple[float, str, str]] = []
_log = llm.log


def log(tag: str, text: str):
    EVENTS.append((time.time(), tag, text))
    _log(tag, text)


llm.log = log  # every module logs through llm.log, so the summary sees every step
TIMES: dict[str, list[float]] = {"model": [], "browser": []}
_chat = llm.chat


async def timed_chat(*args, **kwargs):
    """Every model call's duration, so a slow run shows whether the model or the browser took the time."""
    started = time.time()
    try:
        return await _chat(*args, **kwargs)
    finally:
        TIMES["model"].append(time.time() - started)
        if time.time() - started > 60:
            log("timing", f"model call took {time.time() - started:.0f}s")


llm.chat = timed_chat


class Recorder:
    """Raw HTML of every page and response an agent's browser saw, deduplicated by content."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.index: list[dict] = []
        self.seen: set[str] = set()
        folder.mkdir(parents=True, exist_ok=True)

    def save(self, url: str, kind: str, body: bytes, suffix: str):
        digest = hashlib.sha1(body).hexdigest()[:12]
        if digest in self.seen:
            return
        self.seen.add(digest)
        name = f"{len(self.index):04d}-{kind}{suffix}"
        (self.folder / name).write_bytes(body)
        self.index.append({"file": name, "url": url, "kind": kind, "time": round(time.time() - llm.T0, 1)})

    async def on_response(self, response):
        try:
            kind = response.request.resource_type
            if kind not in ("document", "fetch", "xhr"):
                return
            ctype = response.headers.get("content-type", "")
            body = await response.body()
            suffix = ".html" if "html" in ctype else ".pdf" if "pdf" in ctype else ".zip" if "zip" in ctype else ".bin"
            self.save(response.url, f"response-{kind}", body, suffix)
        except Exception:  # noqa: BLE001  a response that closed before its body was read
            pass

    async def snapshot(self, page):
        """The rendered DOM (after scripts) of the page and each of its frames."""
        for frame in page.frames:
            try:
                self.save(frame.url, "dom", (await frame.content()).encode(), ".html")
            except Exception:  # noqa: BLE001
                pass

    def write_index(self):
        (self.folder / "index.json").write_text(json.dumps(self.index, indent=1, ensure_ascii=False))


MUTATIONS = (Path(__file__).parent / "mutations.js").read_text()
MUTATED: Counter = Counter()
SWEEP: dict = {}


async def mutator(playwright, seed: int):
    """A route handler that rewrites read-only HTML pages with mutations.js in a separate script-free page."""
    browser = await playwright.chromium.launch(headless=True)
    scratch = await (await browser.new_context(java_script_enabled=False)).new_page()
    lock = asyncio.Lock()

    async def handle(route):
        request = route.request
        if request.method != "GET" or request.resource_type not in ("document", "fetch", "xhr"):
            return await route.continue_()
        try:
            response = await route.fetch()
        except Exception:  # noqa: BLE001  the real site was too slow: fail this request, the agent retries
            return await route.abort()
        body = await response.text() if "html" in response.headers.get("content-type", "") else None
        if body is None or re.search(r"type=[\"']?password|<form[^>]+method=[\"']?post", body, re.I):
            return await route.fulfill(response=response)
        async with lock:
            await scratch.set_content(body, wait_until="domcontentloaded")
            stats = await scratch.evaluate(f"({MUTATIONS})(opts)", {"seed": seed, "base": request.url})
            body = await scratch.content()
        MUTATED.update({k: v for k, v in stats.items()} | {"pages": 1})
        await route.fulfill(response=response, body=body)
    return browser, handle


S4_LINK = "/s4-moved-attachment"


def s4_routes(page_file: Path):
    """Route handlers for S4: hide one recorded message from the mailbox, serve it on the tender portal."""
    index = json.loads((page_file.parent / "index.json").read_text())
    url = next(e["url"] for e in index if e["file"] == page_file.name)
    message = re.search(r"([\w-]+)$", url.rstrip("/")).group(1)
    body = page_file.read_text(errors="ignore")

    async def mailbox(route):
        if message in route.request.url:
            return await route.fulfill(status=404, content_type="text/html", body="<h1>Nicht gefunden</h1>")
        if route.request.resource_type not in ("document", "fetch", "xhr"):
            return await route.continue_()
        try:
            response = await route.fetch()
        except Exception:  # noqa: BLE001  the real site was too slow: fail this request, the agent retries
            return await route.abort()
        if "html" not in response.headers.get("content-type", ""):
            return await route.fulfill(response=response)
        text = await response.text()
        text = re.sub(r"<tr\b(?:(?!<tr\b).)*?" + re.escape(message) + r".*?</tr>", "", text, flags=re.S)
        await route.fulfill(response=response, body=text)

    async def portal(route):
        if route.request.url.split("?")[0].endswith(S4_LINK):
            return await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
        if route.request.resource_type != "document":
            return await route.continue_()
        try:
            response = await route.fetch()
        except Exception:  # noqa: BLE001  the real site was too slow: fail this request, the agent retries
            return await route.abort()
        if "html" not in response.headers.get("content-type", ""):
            return await route.fulfill(response=response)
        link = f'<p><a href="{S4_LINK}">Anlage: weitergeleitete Mitteilung zur Vergabe</a></p>'
        await route.fulfill(response=response, body=(await response.text()).replace("</body>", link + "</body>", 1))
    return mailbox, portal, message


class RecordingTab(Tab):
    def __init__(self, page, site, recorder: Recorder):
        super().__init__(page, site)
        self.recorder = recorder

    async def read(self, offset: int = 0, compact: bool = False) -> str:
        text = await super().read(offset, compact)
        await self.recorder.snapshot(self.page)
        return text

    async def act(self, action: str, args: dict) -> str:
        if action == "fetch":  # timed in fetch below
            return await super().act(action, args)
        started = time.time()
        try:
            return await super().act(action, args)
        finally:
            took = time.time() - started
            TIMES["browser"].append(took)
            if took > 20:
                log("timing", f"browser {action} took {took:.0f}s")

    async def fetch(self, url: str) -> str:
        started = time.time()
        try:
            return await super().fetch(url)
        finally:
            took = time.time() - started
            TIMES["browser"].append(took)
            if took > 20:
                log("timing", f"browser fetch took {took:.0f}s")


async def open_tab(playwright, browsers: list, entry: dict, recorder: Recorder, mutate=None, extra=None) -> RecordingTab:
    browser = await playwright.chromium.launch(headless=os.environ.get("HEADLESS") == "1")
    browsers.append(browser)
    context = await browser.new_context()
    if mutate:
        await context.route("**/*", mutate)
    if extra:
        await context.route("**/*", extra)
    context.on("response", recorder.on_response)
    page = await context.new_page()
    try:
        await page.goto(entry["url"], wait_until="domcontentloaded")
    except Exception as error:  # noqa: BLE001  the agent opens the URL itself
        log("runner", f"first load failed: {type(error).__name__}")
    return RecordingTab(page, entry, recorder)


def summary(tag_prefix: str, started: float, ended: float, result: dict) -> dict:
    """Turns, tool calls, repeated URLs and time of one agent, from its log lines."""
    lines = [text for _, tag, text in EVENTS if tag == tag_prefix]
    calls = [m for m in (re.match(r"(\d+): (\w+) (.*)", text) for text in lines) if m]
    urls = Counter()
    for m in calls:
        if m.group(2) in ("goto", "fetch", "save_evidence"):
            try:
                url = json.loads(m.group(3)).get("url")
            except ValueError:
                url = None
            if url:
                urls[url] += 1
    return {"seconds": round(ended - started), "turns": len({m.group(1) for m in calls}), "tool_calls": len(calls),
            "calls_by_tool": dict(Counter(m.group(2) for m in calls)),
            "repeated_urls": {u: n for u, n in urls.items() if n > 1},
            "refused_finishes": sum(text.startswith("finish refused") for text in lines),
            "forced": bool(result.get("forced")), "evidence": len(result.get("evidence") or []),
            "cut": TAGS.get(tag_prefix, tag_prefix) in orchestration.CUT or tag_prefix in orchestration.CUT}


async def timed(tag: str, job, until: float):
    started = time.time()
    result = await orchestration.safe(tag, job, until)
    return result, summary(tag, started, time.time(), result)


def number(value):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value).replace(",", "."))) if value not in (None, "") else None
    except ValueError:
        return None


def exact_ref(ref: str) -> re.Pattern:
    return re.compile(re.escape(ref) + r"(?![\w-])")


def mail_score(mail: dict, facts: dict) -> list[tuple[str, bool]]:
    """Which record kinds the webmail agent kept for the exact reference (from the kept pages, not its summary)."""
    pages = mail.get("evidence") or []
    ref = exact_ref(facts["tender_reference"])
    rows = []
    for record in facts["mail"]["records"]:
        hit = any(record["sender"] in p and record["subject"].lower() in p.lower() and ref.search(p) for p in pages)
        rows.append((f"mail {record['subject']} from {record['sender']}", hit))
    director = [p for p in pages if facts["mail"]["director_sender"] in p and ref.search(p)]
    rows.append((f"mail director pages {len(director)} >= {facts['mail']['director_approvals_min']}",
                 len(director) >= facts["mail"]["director_approvals_min"]))
    return rows


def requirements_score(requirements: dict, facts: dict) -> list[tuple[str, bool]]:
    got = {str(p.get("position")): p for p in requirements.get("positions") or []}
    rows = []
    for position, want in facts["requirements"].items():
        have = got.get(position, {})
        for key, value in want.items():
            ok = (str(have.get(key, "")).strip() == value) if isinstance(value, str) else number(have.get(key)) == value
            rows.append((f"requirements {position} {key}", ok))
    return rows


def commercials_score(commercials: dict, facts: dict) -> list[tuple[str, bool]]:
    want = facts["commercials"]
    discount = commercials.get("discount") or {}
    rows = [("commercials discount percent", number(discount.get("percent")) == want["discount_percent"]),
            ("commercials discount threshold", number(discount.get("min_order_value")) == want["discount_min_order_value"]),
            ("commercials setup pool fee", number(commercials.get("setup_pool_fee")) == want["setup_pool_fee"]),
            ("commercials fx rate", want["fx_rate"] in [number(v) for v in (commercials.get("fx_rates") or {}).values()]),
            ("commercials metal index", want["metal_index"] in [number(v) for v in (commercials.get("metal_indices") or {}).values()])]
    got = {str(p.get("position")): p for p in commercials.get("positions") or []}
    for position, values in want["positions"].items():
        have = got.get(position, {})
        for key, value in values.items():
            if key == "commitment_max_pieces":
                ok = number((have.get("delivery_commitment") or {}).get("max_pieces")) == value
            elif isinstance(value, bool):
                ok = bool(have.get(key)) == value
            elif isinstance(value, str):
                ok = have.get(key) == value
            else:
                ok = number(have.get(key)) == value
            rows.append((f"commercials {position} {key}", ok))
    return rows


def erp_score(erp: dict, requirements: dict, facts: dict) -> list[tuple[str, bool]]:
    rows = []
    for r in requirements.get("positions") or []:
        key = tuple(str(r.get(k)) for k in SPEC_KEYS)
        found = erp.get(json.dumps(key)) or {}
        want = facts["erp"].get(str(r.get("position")))
        if want:
            rows.append((f"erp {r.get('position')} material", found.get("material_number") == want))
    return rows


def report(rows: list[tuple[str, bool]], out: Path) -> None:
    passed = sum(ok for _, ok in rows)
    for name, ok in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"gather score: {passed}/{len(rows)}")
    (out / "gather-score.json").write_text(json.dumps({"passed": passed, "total": len(rows),
                                                       "rows": [{"check": n, "ok": ok} for n, ok in rows]}, indent=1))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", default=",".join(AGENTS))
    parser.add_argument("--deadline", type=float, default=540, help="seconds each phase-1 agent gets")
    parser.add_argument("--erp-deadline", type=float, default=300, help="seconds each ERP search gets")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--from", dest="previous", type=Path)
    parser.add_argument("--mutate", type=int, help="S2: rewrite read-only pages with this seed")
    parser.add_argument("--s4", type=Path, help="S4: recorded mail message page to move to the tender portal")
    args = parser.parse_args()
    chosen = [a for a in args.agents.split(",") if a]
    unknown = set(chosen) - set(AGENTS)
    if unknown:
        raise SystemExit(f"unknown agents {unknown}; choose from {AGENTS}")
    if args.mutate is not None and args.s4:  # each installs a route for every request; only one of them would run
        raise SystemExit("--mutate (S2) and --s4 (S4) are separate stress levels: run them one at a time")
    out = args.out or ROOT / "tools/stress/runs" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    task, _ = contract.load_run()
    facts = json.loads((ROOT / "eval/public-1/gather-facts.json").read_text())

    roles = await resolvers.sites(task)
    log("runner", json.dumps({role: entry["siteId"] for role, entry in roles.items()}))
    results: dict[str, dict] = {}
    if args.previous:
        for name in AGENTS:
            path = args.previous / f"{name}.json"
            if path.exists() and name not in chosen:
                results[name] = json.loads(path.read_text())["result"]
    summaries: dict[str, dict] = {}
    browsers: list = []
    recorders: dict[str, Recorder] = {}
    requirements = None
    erp_found: dict[str, dict] = {}
    async with async_playwright() as playwright:
        try:
            mutate = None
            if args.mutate is not None:
                scratch, mutate = await mutator(playwright, args.mutate)
                browsers.append(scratch)
            extra: dict = {}
            if args.s4:
                mailbox_route, portal_route, moved = s4_routes(args.s4)
                extra = {"webmail": mailbox_route, "tender_portal": portal_route}
                log("s4", f"message {moved} moved from the mailbox to the tender portal")
            tabs = {}
            for name in chosen:
                recorders[name] = Recorder(out / "html" / name)
                tabs[name] = await open_tab(playwright, browsers, roles[name], recorders[name], mutate, extra.get(name))
            deadline = time.time() + args.deadline
            jobs = {"tender_portal": lambda: tender_portal.run(task, tabs["tender_portal"], deadline),
                    "supplier_portal": lambda: supplier_portal.run(task, tabs["supplier_portal"], deadline),
                    "webmail": lambda: webmail.run(task, tabs["webmail"], deadline),
                    "erp": lambda: erp_agent.login(task, tabs["erp"], deadline)}
            done = await asyncio.gather(*(timed(TAGS[name], jobs[name](), deadline + 30) for name in chosen))
            for name, (result, info) in zip(chosen, done):
                results[name], summaries[name] = result, info

            if args.requirements:
                requirements = json.loads(args.requirements.read_text())
            elif args.resolve and all(n in results for n in ("tender_portal", "supplier_portal", "webmail")):
                started = time.time()
                requirements = await orchestration.safe("requirements", resolvers.requirements(
                    task, results["tender_portal"], results["supplier_portal"], results["webmail"]), time.time() + 240)
                summaries["requirements"] = {"seconds": round(time.time() - started)}
            if requirements is not None:
                (out / "requirements.json").write_text(json.dumps(requirements, indent=1, ensure_ascii=False))

            if "erp" in chosen and requirements:
                distinct: dict[tuple, dict] = {}
                for r in requirements.get("positions") or []:
                    distinct.setdefault(tuple(str(r.get(k)) for k in SPEC_KEYS), {k: r.get(k) for k in SPEC_KEYS})
                erp_deadline = time.time() + args.erp_deadline

                async def search(key, req, first):
                    tab = tabs["erp"] if first else await orchestration.fresh(tabs["erp"])
                    tag = f"erp:{req.get('catalogue_group')}"
                    result, info = await timed(tag, erp_agent.run(task, tab, req, erp_deadline - 30), erp_deadline)
                    return key, result, info

                for key, result, info in await asyncio.gather(*(search(k, r, i == 0)
                                                                for i, (k, r) in enumerate(distinct.items()))):
                    erp_found[json.dumps(key)] = result
                    summaries[f"erp:{key[-1]}"] = info
                (out / "erp.json").write_text(json.dumps(erp_found, indent=1, ensure_ascii=False))

            others = [results["supplier_portal"]] if "supplier_portal" in results else []  # as agent.main passes
            if args.s4 and args.resolve and requirements:
                first = await orchestration.safe("commercials", resolvers.commercials(
                    task, results["tender_portal"], results["webmail"], others), time.time() + 300)
                (out / "commercials-first-pass.json").write_text(json.dumps(first, indent=1, ensure_ascii=False))
                SWEEP["first"] = commercials_score(first, facts)
                open_facts = [g for g in sweep_agent.gaps(results["tender_portal"], {}, first)
                              if g["resolver"] == "commercials"]  # as agent.main: commercial facts, during the ERP stage
                log("s4", f"open facts after the first pass: {[g['fact'] for g in open_facts]}")
                started = time.time()
                swept = await sweep_agent.sweep(task, tabs, open_facts, time.time() + 240) if open_facts else {}
                summaries["sweep"] = {"seconds": round(time.time() - started), "gaps": len(open_facts),
                                      "pages": {k: len(v) for k, v in swept.items()}}
                if swept.get("commercials"):  # the swept pages reach the resolver as more tender-portal evidence
                    results["tender_portal"] = {**results["tender_portal"], "evidence":
                                                (results["tender_portal"].get("evidence") or []) + swept["commercials"]}
        finally:
            for name, recorder in recorders.items():
                recorder.write_index()
            for browser in browsers:
                try:
                    await browser.close()
                except Exception as error:  # noqa: BLE001  a request still pending must not lose the run's score
                    log("runner", f"browser close failed: {type(error).__name__}")

    for name in chosen:
        (out / f"{name}.json").write_text(json.dumps({"result": results[name], "summary": summaries[name]},
                                                     indent=1, ensure_ascii=False))
    rows: list[tuple[str, bool]] = []
    if "webmail" in results:
        rows += mail_score(results["webmail"], facts)
    if requirements:
        rows += requirements_score(requirements, facts)
        if erp_found:
            rows += erp_score(erp_found, requirements, facts)
    if args.resolve and "tender_portal" in results and "webmail" in results:
        started = time.time()
        others = [results["supplier_portal"]] if "supplier_portal" in results else []  # as agent.main passes
        commercials = await orchestration.safe("commercials", resolvers.commercials(
            task, results["tender_portal"], results["webmail"], others), time.time() + 300)
        summaries["commercials"] = {"seconds": round(time.time() - started)}
        (out / "commercials.json").write_text(json.dumps(commercials, indent=1, ensure_ascii=False))
        rows += commercials_score(commercials, facts)
        if "first" in SWEEP:  # S4: what the first pass got, before the sweep's pages
            first_ok, first_all = sum(ok for _, ok in SWEEP["first"]), len(SWEEP["first"])
            after_ok = sum(ok for name, ok in rows if name.startswith("commercials"))
            log("s4", f"commercials before the sweep {first_ok}/{first_all}, after {after_ok}/{first_all}")
    if MUTATED:
        summaries["mutations"] = dict(MUTATED)
    summaries["timing"] = {kind: {"calls": len(v), "total_s": round(sum(v)), "max_s": round(max(v), 1) if v else 0,
                                  "mean_s": round(sum(v) / len(v), 1) if v else 0} for kind, v in TIMES.items()}
    (out / "summary.json").write_text(json.dumps(summaries, indent=1))
    print("\n=== step summary")
    for name, info in summaries.items():
        print(f"  {name}: {json.dumps(info)}")
    if rows:
        print("=== gather score")
        report(rows, out)
    print(f"fixture: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
