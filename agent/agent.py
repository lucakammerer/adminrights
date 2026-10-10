"""RFQ agent: models investigate the four websites in parallel, models resolve the evidence by the brief's rules,
code does the arithmetic, and a model enters and signs the bid. Each agent lives in agents/<name>/."""
import asyncio
import contextvars
import json
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
from agents.tender_portal import agent as tender_portal
from agents.webmail import agent as webmail
from browser import Tab


CUT: set[str] = set()  # stages cut at their deadline: their task may still hold its tab for a moment


def start(job, until: float) -> asyncio.Task:
    """Run a job as its own task whose model calls end by `until`."""
    context = contextvars.copy_context()
    context.run(llm.UNTIL.set, until)
    task = asyncio.create_task(job, context=context)
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # a late failure after a cut stays quiet
    return task


async def safe(tag: str, job, until: float, fallback=None):
    """One agent's crash or overrun must not end the run: cut it at `until`, log it and carry on with what the
    others found. A hosted model under load can make every step slow, so phase deadlines are hard: the job's model
    calls end by `until` (llm.UNTIL), and the cut doesn't wait for the job to stop (asyncio.wait_for did, and a model
    call that ignored its cancellation held a 780 s cut until 1093 s)."""
    task = job if isinstance(job, asyncio.Task) else start(job, until)
    await asyncio.wait({task}, timeout=max(1.0, until - time.time()))
    if not task.done():
        task.cancel()
        CUT.add(tag)
        llm.log(tag, "cut at its deadline")
    elif task.exception() is None:
        return task.result()
    else:
        error = task.exception()
        llm.log(tag, f"failed: {type(error).__name__}: {str(error)[:300]}")
    return {} if fallback is None else fallback


async def fresh(tab: Tab) -> Tab:
    """A new tab of the same browser (same login) on the site's start page."""
    page = await tab.page.context.new_page()
    await page.goto(tab.site["url"], wait_until="domcontentloaded")
    return Tab(page, tab.site)


async def main() -> int:
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
            await page.goto(entry["url"], wait_until="domcontentloaded")
            tabs[role] = Tab(page, entry)

        phase1 = end - 10 * 60  # agents wrap up here; hard cut 30 s later
        tender, spec, mail, _ = await asyncio.gather(
            safe("tender-portal", tender_portal.run(task, tabs["tender_portal"], phase1), phase1 + 30),
            safe("supplier-portal", supplier_portal.run(task, tabs["supplier_portal"], phase1), phase1 + 30),
            safe("webmail", webmail.run(task, tabs["webmail"], phase1), phase1 + 30),
            safe("erp-login", erp_agent.login(task, tabs["erp"], phase1), phase1 + 30))
        llm.log("tender-portal", json.dumps(tender, ensure_ascii=False)[:3000])
        llm.log("supplier-portal", json.dumps(spec, ensure_ascii=False)[:3000])
        llm.log("webmail", json.dumps(mail, ensure_ascii=False)[:4000])

        erp_end = end - 6 * 60  # leaves the submission six minutes
        commercials_job = start(resolvers.commercials(task, tender, mail), erp_end + 30)  # only calc needs it
        requirements = await safe("requirements", resolvers.requirements(task, tender, spec, mail), end - 8 * 60) or \
            await safe("requirements", resolvers.requirements(task, tender, spec, mail, effort="low"), erp_end - 60,
                       {"positions": []})
        llm.log("requirements", json.dumps(requirements, ensure_ascii=False))

        erp_tab = tabs["erp"]

        spec_keys = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification", "catalogue_group")
        distinct: dict[tuple, dict] = {}
        for r in requirements["positions"]:
            distinct.setdefault(tuple(str(r.get(k)) for k in spec_keys), {k: r.get(k) for k in spec_keys})

        async def erp_search(req, first):
            tab = erp_tab if first and "erp-login" not in CUT else await fresh(erp_tab)
            result = await erp_agent.run(task, tab, req, erp_end - 30)
            if result.get("forced"):  # cut off: its search did not finish, so it can't have proven "no match"
                result.pop("no_match", None)
            return result

        async def erp_for(key, req, first):
            return key, await safe(f"erp:{req.get('catalogue_group')}", erp_search(req, first), erp_end)

        found = dict(await asyncio.gather(*(erp_for(k, r, i == 0) for i, (k, r) in enumerate(distinct.items()))))
        erp = {r["position"]: found[tuple(str(r.get(k)) for k in spec_keys)] for r in requirements["positions"]}
        llm.log("erp", json.dumps(erp, ensure_ascii=False)[:4000])
        commercials = await safe("commercials", commercials_job, erp_end + 30)
        llm.log("commercials", json.dumps(commercials, ensure_ascii=False))

        facts = calc.facts(tender, requirements, commercials, erp)
        result = calc.compute(facts)
        llm.log("facts", json.dumps(facts, ensure_ascii=False))
        llm.log("calc", result["trace"])
        llm.log("answer", json.dumps(result["answer"], ensure_ascii=False))

        specs = {r["position"]: ", ".join(f"{k} {r.get(k)}" for k in spec_keys) for r in requirements["positions"]}
        # a phase-1 agent that was cut may still be acting on its tab: the submission then works in a tab of its own
        portal = await fresh(tabs["tender_portal"]) if "tender-portal" in CUT else tabs["tender_portal"]
        mailbox = await fresh(tabs["webmail"]) if "webmail" in CUT else tabs["webmail"]
        outcome = await safe("submit", submit_agent.run(task, portal, mailbox, result["answer"], result["omitted"],
                                                        specs, mail.get("own_address", ""), end - 20), end)
        llm.log("submit", json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

