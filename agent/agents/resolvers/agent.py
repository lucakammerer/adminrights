"""Resolvers: apply the brief's rules to the kept evidence, without a browser. See README.md."""
import asyncio
import json

import llm
from agents.common import RESOLVE, context, evidence, mentions, technical_records

ROLES = {
    "tender_portal": "the public tender, its bill of quantities, the bidder Q&A and the bid submission",
    "supplier_portal": "the buyer's technical specification and its revisions",
    "erp": "the company's materials, stock, lead times and price conditions",
    "webmail": "the sales mailbox with the approvals and the signing TAN",
}


SITES_TIMEOUT = 60  # seconds per attempt, so one slow call still leaves room for the second before elimination


async def sites(task) -> dict:
    """Which website plays which role, judged from the brief: names and ids differ between datasets. Never raises
    (F21): the run's submission target is the tender portal, the model assigns the other roles, and a role it leaves
    open gets a remaining website by elimination."""
    by_id = {s["siteId"]: s for s in task["access"]}
    chosen: dict[str, str] = {}
    target = (task.get("submission") or {}).get("siteId")
    if target in by_id:
        chosen["tender_portal"] = target

    for _ in range(2):
        open_roles = {role: text for role, text in ROLES.items() if role not in chosen}
        free = [{"siteId": s["siteId"], "url": s["url"]} for s in task["access"] if s["siteId"] not in chosen.values()]
        fixed = "".join(f"\n{role} is already {site_id}." for role, site_id in chosen.items())
        question = f"""{context(task)}

Websites: {json.dumps(free)}{fixed}
Assign each of these roles exactly one of the websites above by its siteId: {json.dumps(open_roles)}
JSON: {{{", ".join(f'"{role}": "<siteId>"' for role in open_roles)}}}"""
        try:
            answer = await asyncio.wait_for(llm.ask_json(RESOLVE, question, effort="low"), timeout=SITES_TIMEOUT)
        except Exception as error:  # noqa: BLE001  elimination below still assigns every role
            llm.log("sites", f"assignment failed: {type(error).__name__}: {str(error)[:200]}")
            continue
        for role in open_roles:
            site_id = answer.get(role)
            if isinstance(site_id, str) and site_id in by_id and site_id not in chosen.values():
                chosen[role] = site_id
        if len(chosen) == len(ROLES):
            break

    free_ids = [site_id for site_id in by_id if site_id not in chosen.values()]
    for role in ROLES:
        if role not in chosen:
            chosen[role] = free_ids.pop(0) if free_ids else next(iter(by_id))
            llm.log("sites", f"{role}: no clear assignment, took {chosen[role]} by elimination")
    return {role: by_id[chosen[role]] for role in ROLES}


async def first(*jobs):
    """The first of several identical calls to answer; the others are cancelled."""
    tasks = [asyncio.ensure_future(job) for job in jobs]
    try:
        for done in asyncio.as_completed(tasks):
            try:
                return await done
            except Exception as error:  # noqa: BLE001  another call may still answer
                failed = error
        raise failed
    finally:
        for job in tasks:
            job.cancel()


async def requirements(task, tender, spec, mail, effort: str = "medium") -> dict:
    # Only the technical release matters here; every other mail would slow this critical-path call. Which record that
    # is comes from this run's brief (its subject and sender); a brief that names none gets all kept mail.
    pages = mail.get("evidence", [])
    records = technical_records(task["brief"])
    technical = {"evidence": [page for page in pages if mentions(page, records)] or pages}
    question = f"""{context(task)}

Evidence from the tender portal:
{evidence(tender)}

Evidence from the supplier portal:
{evidence(spec)}

Technical releases from the mailbox:
{evidence(technical)}

Decide from the pages kept as evidence: the agents' own summaries above them can be incomplete or wrong.
For every tender position, work out:
- final_quantity_pieces: tender quantity, replaced by the latest dated clarification that changes it, converted to
  pieces with the governing revision's pieces per set when the unit is a set. A withdrawn answer counts as if it had
  never been given: the latest change that is not withdrawn still applies, even when it is older than the withdrawn
  one. List every quantity clarification for the position in quantity_reasoning before you decide;
- the governing requirement: the current revision's requirement, with the latest applicable scoped technical
  amendments (only those naming that revision and requirement, only the named attributes); if the stroke is a usable
  stroke, add twice the per-end reserve of its key from the latest technical release for that revision to get the
  nominal stroke.
JSON: {{"positions": [{{"position": "...", "final_quantity_pieces": 0, "quantity_reasoning": "...",
"requirement": "the requirement id the position refers to", "bore_mm": 0, "stroke_mm": 0, "pressure_bar": 0, "mounting": "...", "certification": "...",
"catalogue_group": "...", "requirement_reasoning": "..."}}]}}"""
    llm.log("requirements", f"asking twice with {len(question)} chars, effort {effort}")  # its size drives the critical path
    # it holds up the ERP phase, and one hosted call in a few hangs until its timeout: the faster of two answers
    return await first(llm.ask_json(RESOLVE, question, effort=effort), llm.ask_json(RESOLVE, question, effort=effort))


async def commercials(task, tender, mail) -> dict:
    question = f"""{context(task)}

Evidence from the tender portal:
{evidence(tender)}

Messages from the sales mailbox:
{evidence(mail)}

Decide from the pages kept as evidence: the agents' own summaries above them can be incomplete or wrong.
Resolve, by the brief's rules (exact reference, authorized sender, latest record no later than the scenario date,
newer replaces older, future-dated records never apply):
- discount: the latest director approval for this exact reference: percent and, if it is conditional, its minimum
  undiscounted net order value (else null);
- per position: which condition group (the brief's term) applies and therefore whether the discount applies to "base",
  "base_and_surcharge" or "none" (no group: "base"); the packaging tariff in EUR per carton; the delivery commitment
  assigned to it (material number, max pooled pieces, weeks) or null; whether it is a setup-pool member; whether it
  is a project-bonus member; any ordinary setup fee in EUR stated for it (else 0);
- fx_rates: EUR per one unit of each foreign currency, by FX key; metal_indices: EUR per kg by index key, the rate
  valid on the scenario date; setup_pool_fee in EUR; project_bonus_bands as marginal bands.
JSON: {{"tender_reference": "the exact reference", "discount": {{"percent": 0, "min_order_value": null, "source": "..."}},
"positions": [{{"position": "...", "discount_applies_to": "base", "carton_price": 0,
"delivery_commitment": {{"material_number": "...", "max_pieces": 0, "weeks": 0}} or null,
"setup_pool_member": false, "project_bonus_member": false, "setup_fee": 0, "reasoning": "..."}}],
"fx_rates": {{"<FX key>": 0.0}}, "metal_indices": {{"<index key>": 0.0}}, "setup_pool_fee": 0,
"project_bonus_bands": [{{"from": 0, "to": null, "percent": 0}}]}}
Every amount, rate and percent is a plain JSON number (decimal point, no units)."""
    llm.log("commercials", f"asking with {len(question)} chars")
    return await llm.ask_json(RESOLVE, question, effort="medium")
