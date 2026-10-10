"""RFQ agent: models investigate the four websites in parallel, models resolve the evidence by the brief's rules,
code does the arithmetic, and a model enters and signs the bid. Each agent lives in agents/<name>/."""
import asyncio
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


async def safe(tag: str, job, fallback=None):
    """One agent's crash must not end the run: log it and carry on with what the others found."""
    try:
        return await job
    except Exception as error:  # noqa: BLE001
        llm.log(tag, f"failed: {type(error).__name__}: {str(error)[:300]}")
        return {} if fallback is None else fallback


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

        phase1 = end - 9 * 60
        tender, spec, mail, _ = await asyncio.gather(
            safe("tender-portal", tender_portal.run(task, tabs["tender_portal"], phase1)),
            safe("supplier-portal", supplier_portal.run(task, tabs["supplier_portal"], phase1)),
            safe("webmail", webmail.run(task, tabs["webmail"], phase1)),
            safe("erp-login", erp_agent.login(task, tabs["erp"], phase1)))
        llm.log("tender-portal", json.dumps(tender, ensure_ascii=False)[:3000])
        llm.log("supplier-portal", json.dumps(spec, ensure_ascii=False)[:3000])
        llm.log("webmail", json.dumps(mail, ensure_ascii=False)[:4000])

        commercials_job = asyncio.create_task(resolvers.commercials(task, tender, mail))  # only calc needs it
        requirements = await resolvers.requirements(task, tender, spec, mail)
        llm.log("requirements", json.dumps(requirements, ensure_ascii=False))

        erp_tab = tabs["erp"]

        spec_keys = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification", "catalogue_group")
        distinct: dict[tuple, dict] = {}
        for r in requirements["positions"]:
            distinct.setdefault(tuple(str(r.get(k)) for k in spec_keys), {k: r.get(k) for k in spec_keys})

        async def erp_for(key, req, first):
            tab = erp_tab
            if not first:
                page = await erp_tab.page.context.new_page()
                await page.goto(erp_tab.site["url"], wait_until="domcontentloaded")
                tab = Tab(page, erp_tab.site)
            return key, await safe(f"erp:{req.get('catalogue_group')}", erp_agent.run(task, tab, req, end - 6 * 60))

        found = dict(await asyncio.gather(*(erp_for(k, r, i == 0) for i, (k, r) in enumerate(distinct.items()))))
        erp = {r["position"]: found[tuple(str(r.get(k)) for k in spec_keys)] for r in requirements["positions"]}
        llm.log("erp", json.dumps(erp, ensure_ascii=False)[:4000])
        commercials = await safe("commercials", commercials_job)
        llm.log("commercials", json.dumps(commercials, ensure_ascii=False))

        facts = calc.facts(tender, requirements, commercials, erp)
        result = calc.compute(facts)
        llm.log("facts", json.dumps(facts, ensure_ascii=False))
        llm.log("calc", result["trace"])
        llm.log("answer", json.dumps(result["answer"], ensure_ascii=False))

        specs = {r["position"]: ", ".join(f"{k} {r.get(k)}" for k in spec_keys) for r in requirements["positions"]}
        outcome = await submit_agent.run(task, tabs["tender_portal"], tabs["webmail"], result["answer"], result["omitted"], specs,
                                   mail.get("own_address", ""), end - 20)
        llm.log("submit", json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

