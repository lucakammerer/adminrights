"""RFQ agent: models investigate the four websites in parallel, models resolve the evidence by the brief's rules,
code does the arithmetic, and a model enters and signs the bid. Each agent lives in agents/<name>/."""
import asyncio
import contextvars
import json
import os
import sys
import time

from playwright.async_api import async_playwright

import browsers
import calc
import llm
import run as contract
from agents.erp import agent as erp_agent
from agents.resolvers import agent as resolvers
from agents.submit import agent as submit_agent
from agents.supplier_portal import agent as supplier_portal
from agents.sweep import agent as sweep
from agents.tender_portal import agent as tender_portal
from agents.webmail import agent as webmail
from browser import Tab


CUT: set[str] = set()  # stages cut at their deadline: their task may still hold its tab for a moment
# Specifications plus technical releases give the ERP search keys before the tender agent completes. The later
# requirements resolver is still authoritative: a tender clarification can change a key, in which case that position
# receives its own search and unused early searches are stopped. Without an early search, requirements must leave the
# ERP agents ERP_SEARCH_MIN seconds. A low-effort resolver attempt joins after BACKUP_AFTER seconds.
ERP_SEARCH_MIN = 60
BACKUP_AFTER = 60
SPEC_KEYS = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification", "catalogue_group")
OPEN_TIMEOUT = 20  # seconds to open a new tab on a site's start page (pages load in 1-5 s)


def start(job, until: float, cap: float | None = None) -> asyncio.Task:
    """Run a job as its own task whose model calls end by `until` and take at most `cap` each. The pages its agents
    keep stay readable as `task.kept`, for a cut."""
    context = contextvars.copy_context()
    context.run(llm.UNTIL.set, until)
    if cap:
        context.run(llm.CAP.set, cap)
    kept: list[list[str]] = []
    context.run(llm.KEPT.set, kept)
    task = asyncio.create_task(job, context=context)
    task.kept = kept
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # a late failure after a cut stays quiet
    return task


def kept_pages(task: asyncio.Task) -> list[str]:
    """Every page the job's agents kept so far, each once."""
    return list(dict.fromkeys(page for pages in getattr(task, "kept", []) for page in pages))


async def safe(tag: str, job, until: float, fallback=None, cap: float | None = None):
    """One agent's crash or overrun must not end the run: cut it at `until`, log it and carry on with what the
    others found. A hosted model under load can make every step slow, so phase deadlines are hard: the job's model
    calls end by `until` (llm.UNTIL), and the cut doesn't wait for the job to stop (asyncio.wait_for did, and a model
    call that ignored its cancellation held a 780 s cut until 1093 s). A job that is cut or fails still hands on the
    pages its agents kept, marked `forced`: one webmail agent had kept every message and then stalled."""
    task = job if isinstance(job, asyncio.Task) else start(job, until, cap)
    await asyncio.wait({task}, timeout=max(1.0, until - time.time()))
    if not task.done():
        task.cancel()
        CUT.add(tag)
        llm.log(tag, "cut at its deadline")
    elif task.cancelled():
        llm.log(tag, "cancelled")
    elif task.exception() is None:
        return task.result()
    else:
        error = task.exception()
        llm.log(tag, f"failed: {type(error).__name__}: {str(error)[:300]}")
    result = {} if fallback is None else fallback
    if pages := kept_pages(task):
        llm.log(tag, f"handing on {len(pages)} kept pages")
        result = {**result, "evidence": pages, "forced": True}
    return result


def positions(requirements) -> list[dict]:
    """The resolver's rows that name a position: a malformed answer must not end the run. The position keeps its type
    as written, because calc.facts matches it against the commercials resolver's rows."""
    def named(position) -> bool:
        return (isinstance(position, str) and bool(position.strip())) or \
            (isinstance(position, (int, float)) and not isinstance(position, bool))

    rows = requirements.get("positions") if isinstance(requirements, dict) else None
    return [r for r in rows if isinstance(r, dict) and named(r.get("position"))] if isinstance(rows, list) else []


def governing(answer) -> list[dict]:
    """The early-specs rows that contain at least one ERP search key."""
    rows = answer.get("requirements") if isinstance(answer, dict) else None
    return [r for r in rows if isinstance(r, dict) and any(r.get(k) not in (None, "") for k in SPEC_KEYS)] \
        if isinstance(rows, list) else []


def spec_key(row: dict) -> tuple:
    """The ERP-relevant values in a stable form, so 200 and 200.0 (or case/space variants) share one search."""
    def normal(value) -> str:
        text = "".join(str("" if value is None else value).split()).casefold()
        try:
            return repr(float(text))
        except ValueError:
            return text
    return tuple(normal(row.get(k)) for k in SPEC_KEYS)


async def resolve(tag: str, ask, until: float, rows) -> list[dict]:
    """Use the first valid resolver answer, with a low-effort hedge only after the normal call has had time to answer."""
    if until <= time.time():
        llm.log(tag, "no time left for a resolver call")
        return []
    cap = until - time.time()
    first, backup = start(ask("medium"), until, cap), None
    try:
        await asyncio.wait({first}, timeout=max(0.0, min(BACKUP_AFTER, cap)))
        answered = first.done() and not first.cancelled() and first.exception() is None and rows(first.result())
        backup = None if answered else start(ask("low"), until, cap)
        found = rows(await safe(tag, first, until))
        if found or backup is None:
            return found
        llm.log(tag, "first attempt brought nothing: taking the low-effort one")
        return rows(await safe(tag, backup, until))
    finally:
        for job in (first, backup):
            if job:
                job.cancel()


async def resolve_requirements(inputs: tuple, until: float) -> list[dict]:
    """The authoritative position requirements by `until`."""
    return await resolve("requirements", lambda effort: resolvers.requirements(*inputs, effort=effort), until, positions)


def bid(tender: dict, requirements: dict, commercials: dict, erp: dict) -> dict:
    """calc's answer. If the facts of one position break it, the others still count: a position whose facts can't be
    built or computed loses its ERP finding, or if that is not enough the position itself, and is omitted as
    unfinished (never no_bid); if even that fails, an answer with the reference and every position omitted, so the
    run still signs."""
    def compute(rows: list[dict], found: dict) -> dict:
        facts = calc.facts(tender, {"positions": rows}, commercials, found)
        llm.log("facts", json.dumps(facts, ensure_ascii=False))
        return calc.compute(facts)

    rows = requirements["positions"]
    try:
        return compute(rows, erp)
    except Exception as error:  # noqa: BLE001
        llm.log("calc", f"failed: {type(error).__name__}: {str(error)[:300]}; retrying position by position")
    kept_rows, found, dropped = [], {}, []
    for row in rows:
        key = row["position"]
        for finding in (erp.get(key) or {}, {}):
            try:
                calc.compute(calc.facts(tender, {"positions": [row]}, commercials, {key: finding}))
            except Exception as error:  # noqa: BLE001
                llm.log("calc", f"{key}: {type(error).__name__}: {str(error)[:200]}")
                continue
            kept_rows.append(row)
            found[key] = finding
            break
        else:
            dropped.append(key)
    try:
        result = compute(kept_rows, found)
        return {**result, "omitted": result["omitted"] + dropped}
    except Exception as error:  # noqa: BLE001
        llm.log("calc", f"failed again: {type(error).__name__}: {str(error)[:300]}; every position omitted")
    reference = next((r for r in (commercials.get("tender_reference"), tender.get("tender_reference"))
                      if isinstance(r, str) and r), "")
    return {**calc.compute({"tender_reference": reference, "positions": []}), "omitted": [r["position"] for r in rows]}


async def fresh(tab: Tab) -> Tab:
    """A new tab of the same browser (same login) on the site's start page, within OPEN_TIMEOUT, and never an error:
    it opens the ERP searches' tabs inside their time and the submission's outside any stage, where a failed load
    would end the run unsigned. A start page that doesn't load leaves the agent the new tab to open the URL itself
    (its mission names it); a tab that doesn't open leaves it the old one."""
    try:
        page = await asyncio.wait_for(tab.page.context.new_page(), OPEN_TIMEOUT)
    except Exception as error:  # noqa: BLE001
        llm.log("fresh", f"no new tab ({type(error).__name__}): the old one for {tab.site.get('url')}")
        return tab
    try:
        await asyncio.wait_for(page.goto(tab.site["url"], wait_until="domcontentloaded"), OPEN_TIMEOUT)
    except Exception as error:  # noqa: BLE001
        llm.log("fresh", f"start page not loaded ({type(error).__name__}): {tab.site.get('url')}")
    return Tab(page, tab.site)


async def main() -> int:
    CUT.clear()  # local tests may run main more than once in one interpreter; a previous run's cut is never relevant
    started = time.time()
    task, token = contract.load_run()
    budget = min(contract.seconds_left(task), 19 * 60)
    end = started + budget
    llm.log("run", f"{task.get('run_id') or '(local scouting)'}; {budget:.0f}s budget")
    roles_job = asyncio.create_task(resolvers.sites(task))
    async with async_playwright() as playwright:
        count = max(1, min(4, len(browsers.cdp_urls()) or 4))
        tabs = {}
        pages = []
        for i in range(4):
            _, page = await browsers.connect(playwright, i if i < count else 0)
            if i >= count:
                page = await page.context.new_page()
            pages.append(page)
        roles = await roles_job
        llm.log("sites", json.dumps({role: entry["siteId"] for role, entry in roles.items()}))
        for (role, entry), page in zip(roles.items(), pages):
            try:
                await page.goto(entry["url"], wait_until="domcontentloaded")
            except Exception as error:  # noqa: BLE001  a slow site must not end the run: its agent opens the URL itself
                llm.log(role, f"first load failed: {type(error).__name__}")
            tabs[role] = Tab(page, entry)

        phase1 = end - 10 * 60  # agents wrap up here; hard cut 30 s later
        tender_job, spec_job, mail_job, login_job = (asyncio.create_task(job) for job in (
            safe("tender-portal", tender_portal.run(task, tabs["tender_portal"], phase1), phase1 + 30),
            safe("supplier-portal", supplier_portal.run(task, tabs["supplier_portal"], phase1), phase1 + 30),
            safe("webmail", webmail.run(task, tabs["webmail"], phase1), phase1 + 30),
            safe("erp-login", erp_agent.login(task, tabs["erp"], phase1), phase1 + 30)))

        erp_end = end - 6 * 60  # leaves the submission six minutes
        erp_search_end = erp_end - 30 - erp_agent.FINISH_GRACE  # where each ERP agent's own search must end
        erp_tab = tabs["erp"]
        searches: dict[tuple, tuple[str, asyncio.Task]] = {}

        async def erp_search(req, first):
            tab = erp_tab if first and "erp-login" not in CUT else await fresh(erp_tab)
            result = await erp_agent.run(task, tab, req, erp_end - 30)
            if result.get("forced"):  # cut off: its search did not finish, so it can't have proven "no match"
                result.pop("no_match", None)
            if result.get("no_match") and erp_end - 30 - time.time() > 150:  # a no_bid costs the bid: confirm it (I11)
                second = await erp_agent.run(task, await fresh(erp_tab), req, erp_end - 30)
                llm.log(f"erp:{req.get('catalogue_group')}", f"no-match check found {second.get('material_number')!r}")
                if second.get("material_number") and not second.get("forced"):
                    return second
            return result

        def search(row: dict):
            """Start one ERP search per distinct governing requirement."""
            if (key := spec_key(row)) not in searches:
                requirement = {k: row.get(k) for k in SPEC_KEYS}
                searches[key] = (f"erp:{requirement.get('catalogue_group')}",
                                 start(erp_search(requirement, not searches), erp_end))

        async def search_early():
            """Search the specification-derived requirements while the tender agent is still collecting Q&A."""
            spec, mail = await asyncio.gather(spec_job, mail_job)
            if not spec.get("evidence"):
                llm.log("specs", "no specification kept: early ERP searches wait for requirements")
                return
            if tender_job.done():
                llm.log("specs", "tender agent already done: requirements decides the search keys")
                return
            rows = await resolve("specs", lambda effort: resolvers.specs(task, spec, mail, effort),
                                 erp_search_end - ERP_SEARCH_MIN, governing)
            llm.log("specs", json.dumps(rows, ensure_ascii=False))
            await login_job
            for row in rows:
                search(row)

        early = asyncio.create_task(search_early())
        early.add_done_callback(lambda task: task.cancelled() or task.exception())
        tender, spec, mail, _ = await asyncio.gather(tender_job, spec_job, mail_job, login_job)
        llm.log("tender-portal", json.dumps(tender, ensure_ascii=False)[:3000])
        llm.log("supplier-portal", json.dumps(spec, ensure_ascii=False)[:3000])
        llm.log("webmail", json.dumps(mail, ensure_ascii=False)[:4000])

        async def sweep_tabs():  # other websites are idle while ERP searches run: use tabs of their own for a sweep
            return {role: await fresh(tabs[role]) for role in ("tender_portal", "supplier_portal", "webmail")}

        # Only calc needs commercial facts. The existing sweep may improve them while the ERP searches run, but its
        # first answer remains usable if it is stopped when calc becomes ready.
        erp_done = asyncio.Event()
        commercials_job = start(sweep.commercials_with_sweep(task, tender, mail, [spec], sweep_tabs, erp_end + 30,
                                                             erp_done), erp_end + 30, erp_end + 30 - time.time())
        requirements_job = asyncio.create_task(resolve_requirements((task, tender, spec, mail), erp_end))
        requirements_cut = erp_search_end - ERP_SEARCH_MIN
        # A completed early resolver may start searches while requirements runs. Until then the resolver must preserve
        # the ERP window; after at least one early search exists, it may use the full ERP stage.
        while not requirements_job.done():
            until = erp_end if searches else requirements_cut
            if time.time() >= until:
                break
            waiting = {requirements_job}
            if not early.done():
                waiting.add(early)
            await asyncio.wait(waiting, timeout=max(0.0, until - time.time()), return_when=asyncio.FIRST_COMPLETED)
            if early.done() and not searches:
                break
        requirements = {"positions": await safe("requirements", requirements_job,
                                                  erp_end if searches else requirements_cut, [])}
        early.cancel()  # after authoritative positions arrive, a late specs answer cannot help
        llm.log("requirements", json.dumps(requirements, ensure_ascii=False))

        early_searches = len(searches)
        for row in requirements["positions"]:
            if spec_key(row) in searches:
                continue
            if time.time() >= erp_search_end:
                llm.log("erp", f"{row['position']}: no time left to search its requirement")
                continue
            if early_searches:
                llm.log("erp", f"{row['position']}: requirement differs from early searches: searching now")
            search(row)
        needed = [key for key in dict.fromkeys(map(spec_key, requirements["positions"])) if key in searches]
        for key, (tag, job) in searches.items():
            if key not in needed and not job.done():
                job.cancel()
                llm.log(tag, "no position needs this early search: stopped")
        found = dict(zip(needed, await asyncio.gather(*(safe(*searches[key], erp_end) for key in needed))))
        erp_done.set()  # a sweep still looking for commercial facts stops: calc must not wait for it
        erp = {row["position"]: found[spec_key(row)] for row in requirements["positions"] if spec_key(row) in found}
        llm.log("erp", json.dumps(erp, ensure_ascii=False)[:4000])
        commercials = await safe("commercials", commercials_job, erp_end + 30)
        llm.log("commercials", json.dumps(commercials, ensure_ascii=False))

        result = bid(tender, requirements, commercials, erp)
        llm.log("calc", result["trace"])
        llm.log("answer", json.dumps(result["answer"], ensure_ascii=False))
        if os.environ.get("DRY_RUN"):  # local scoring stops before anything binding (tools/score.sh)
            return 0
        if (task.get("submission") or {}).get("kind") == "api":  # the run takes its answer by API, not on a website
            try:
                status, body = contract.submit_answer(task, token, result["answer"])
                llm.log("submit", f"answer posted: HTTP {status} {body[:300]}")
            except Exception as error:  # noqa: BLE001
                llm.log("submit", f"posting the answer failed: {type(error).__name__}: {str(error)[:300]}")
            return 0

        specs = {r["position"]: ", ".join(f"{k} {r.get(k)}" for k in SPEC_KEYS) for r in requirements["positions"]}
        # a phase-1 agent that was cut may still be acting on its tab: the submission then works in a tab of its own
        portal = await fresh(tabs["tender_portal"]) if "tender-portal" in CUT else tabs["tender_portal"]
        mailbox = await fresh(tabs["webmail"]) if "webmail" in CUT else tabs["webmail"]
        outcome = await safe("submit", submit_agent.run(task, portal, mailbox, result["answer"], result["omitted"],
                                                        specs, mail.get("own_address", ""), end - 20), end)
        llm.log("submit", json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

