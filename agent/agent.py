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
from agents.common import site
from agents.erp import agent as erp_agent
from agents.mail import agent as mail_agent
from agents.resolvers import agent as resolvers
from agents.spec import agent as spec_agent
from agents.submit import agent as submit_agent
from agents.tender import agent as tender_agent
from browser import Tab


async def main() -> int:
    started = time.time()
    task, token = contract.load_run()
    budget = min(contract.seconds_left(task), 19 * 60)
    end = started + budget
    llm.log("run", f"{task.get('run_id') or '(local scouting)'}; {budget:.0f}s budget")
    async with async_playwright() as playwright:
        count = max(1, min(4, len(browsers.cdp_urls()) or 4))
        tabs = {}
        order = ["tender-portal", "customer-portal", "mail", "erp"]
        pages = []
        for i in range(4):
            _, page = await browsers.connect(playwright, i if i < count else 0)
            if i >= count:
                page = await page.context.new_page()
            pages.append(page)
        for site_id, page in zip(order, pages):
            entry = site(task, site_id)
            await page.goto(entry["url"], wait_until="domcontentloaded")
            tabs[site_id] = Tab(page, entry)

        phase1 = end - 9 * 60
        tender, spec, mail, _ = await asyncio.gather(
            tender_agent.run(task, tabs["tender-portal"], phase1), spec_agent.run(task, tabs["customer-portal"], phase1),
            mail_agent.run(task, tabs["mail"], phase1), erp_agent.login(task, tabs["erp"], phase1))
        llm.log("tender", json.dumps(tender, ensure_ascii=False)[:3000])
        llm.log("spec", json.dumps(spec, ensure_ascii=False)[:3000])
        llm.log("mail", json.dumps(mail, ensure_ascii=False)[:4000])

        requirements, commercials = await asyncio.gather(
            resolvers.requirements(task, tender, spec, mail), resolvers.commercials(task, tender, mail))
        llm.log("requirements", json.dumps(requirements, ensure_ascii=False))
        llm.log("commercials", json.dumps(commercials, ensure_ascii=False))

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
            return key, await erp_agent.run(task, tab, req, end - 6 * 60)

        found = dict(await asyncio.gather(*(erp_for(k, r, i == 0) for i, (k, r) in enumerate(distinct.items()))))
        erp = {r["position"]: found[tuple(str(r.get(k)) for k in spec_keys)] for r in requirements["positions"]}
        llm.log("erp", json.dumps(erp, ensure_ascii=False)[:4000])

        facts = calc.facts(tender, requirements, commercials, erp)
        result = calc.compute(facts)
        llm.log("facts", json.dumps(facts, ensure_ascii=False))
        llm.log("calc", result["trace"])
        llm.log("answer", json.dumps(result["answer"], ensure_ascii=False))

        specs = {r["position"]: ", ".join(f"{k} {r.get(k)}" for k in spec_keys) for r in requirements["positions"]}
        outcome = await submit_agent.run(task, tabs["tender-portal"], tabs["mail"], result["answer"], specs,
                                   mail.get("own_address", ""), end - 20)
        llm.log("submit", json.dumps(outcome, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

