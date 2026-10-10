"""Gap sweep (I16): code lists the facts the first pass left open; for each, one short mission looks for it on the
other websites, where the model chooses what to open. See README.md."""
import asyncio
import time

import llm
from agents.common import BOOL, STR, login_line, obj, system
from agents.resolvers import agent as resolvers
from calc import lookup

SPEC = ("final_quantity_pieces", "bore_mm", "stroke_mm", "pressure_bar", "catalogue_group")
MAX_GAPS = 3  # the most important open facts only: each costs a mission per website
STEPS = 12
RESULT = obj(found=BOOL, fact=STR, where=STR)
SECOND_CALL = 150  # seconds kept for the second commercials call after a sweep (it took 77-317 s on 2026-10-10)
SWEEP_MIN = 90  # seconds a sweep needs to be worth starting


def _missing(value) -> bool:
    return value in (None, "", 0, [], {})


def gaps(tender: dict, requirements: dict, commercials: dict, erp: dict | None = None) -> list[dict]:
    """The open facts, most important first: {"fact": what is missing, "resolver": which one decides it}. Pure code
    over the resolvers' output; nothing is looked up on a website here."""
    found: list[dict] = []
    positions = requirements.get("positions") or []
    listed = [str(p.get("position")) for p in tender.get("positions") or [] if p.get("position")]
    have = {str(p.get("position")) for p in positions}
    for key in listed:
        if key not in have:
            found.append({"fact": f"the final quantity and governing requirement of position {key}",
                          "resolver": "requirements"})
    for p in positions:
        open_fields = [f for f in SPEC if _missing(p.get(f))]
        if open_fields:
            found.append({"fact": f"position {p.get('position')}: {', '.join(open_fields)}", "resolver": "requirements"})
    by_pos = [c for c in commercials.get("positions") or [] if isinstance(c, dict)]
    if any(c.get("setup_pool_member") for c in by_pos) and _missing(commercials.get("setup_pool_fee")):
        found.append({"fact": "the shared setup pool fee and its allocation rule", "resolver": "commercials"})
    if any(c.get("project_bonus_member") for c in by_pos) and _missing(commercials.get("project_bonus_bands")):
        found.append({"fact": "the project bonus bands", "resolver": "commercials"})
    no_tariff = [str(c.get("position")) for c in by_pos if _missing(c.get("carton_price"))]
    if no_tariff:
        found.append({"fact": f"the packaging tariff per carton for position(s) {', '.join(no_tariff)}",
                      "resolver": "commercials"})
    if not (commercials.get("discount") or {}).get("source"):
        found.append({"fact": "the sales director's discount approval for this exact reference", "resolver": "commercials"})
    for key, e in (erp or {}).items():
        pc = (e or {}).get("price_condition") or {}
        currency = str(pc.get("currency") or "EUR").upper()
        if currency != "EUR" and lookup(commercials.get("fx_rates"), pc.get("fx_key"), currency) is None:
            found.append({"fact": f"the FX rate (EUR per {currency}) for key {pc.get('fx_key') or currency}",
                          "resolver": "commercials"})
        if (e or {}).get("surcharge_mass") and lookup(commercials.get("metal_indices"), e.get("price_index_key")) is None:
            found.append({"fact": f"the metal index rate for key {e.get('price_index_key')}", "resolver": "commercials"})
    unique = list({g["fact"]: g for g in found}.values())
    return unique[:MAX_GAPS]


def mission(task: dict, tab, gap: dict) -> str:
    return f"""{login_line(tab.site)} (you may already be logged in)
One fact the bid needs is still open after the first pass: {gap['fact']}.
The brief's rules say where such a record usually is, but this website may hold it instead (a document, a message, a
record, a Q&A answer). Look for it on this website for the exact tender reference only; you choose what to open and
search. Keep every page that states it with save_evidence. If this website does not hold it, finish quickly with
found false. Finish with found, the fact as written and where it is."""


async def sweep(task: dict, tabs: dict, gap_list: list[dict], deadline: float) -> dict[str, list[str]]:
    """One mission per open fact on every website's tab: the tabs work in parallel, each through the facts in turn;
    returns the kept pages per resolver. A tab that fails or runs out of time just contributes nothing more."""
    pages: dict[str, list[str]] = {}

    async def on_tab(role, tab):
        """The open facts one after another on this tab: two loops on one tab would fight over its page."""
        for gap in gap_list:
            try:
                result = await llm.investigate(tab, system(task), mission(task, tab, gap), RESULT, deadline,
                                               f"sweep:{role}", max_steps=STEPS, effort=llm.NAV_EFFORT)
            except Exception as error:  # noqa: BLE001  this tab contributes nothing more
                llm.log(f"sweep:{role}", f"failed: {type(error).__name__}: {str(error)[:200]}")
                return
            if result.get("found") and result.get("evidence"):
                pages.setdefault(gap["resolver"], []).extend(result["evidence"])

    await asyncio.gather(*(on_tab(role, tab) for role, tab in tabs.items()))
    return pages


async def commercials_with_sweep(task: dict, tender: dict, mail: dict, others: list[dict], open_tabs, until: float,
                                 stop: asyncio.Event | None = None) -> dict:
    """The commercials resolver, then a sweep for the commercial facts it left open and, if the sweep kept pages, the
    resolver again with them. Runs alongside the ERP searches on the other websites' tabs (`open_tabs()` gives them)
    and only in time that is free anyway: once `stop` is set (the ERP searches are done, calc is waiting) the first
    answer is returned at once. Never worse than the first answer: a sweep or second call that fails, finds nothing or
    runs out of time keeps it."""
    first = await resolvers.commercials(task, tender, mail, others)
    open_facts = [g for g in gaps(tender, {}, first) if g["resolver"] == "commercials"]
    sweep_until = until - SECOND_CALL
    if not open_facts or sweep_until - time.time() < SWEEP_MIN or (stop and stop.is_set()):
        if open_facts:
            llm.log("sweep", f"no time to look for {[g['fact'] for g in open_facts]}")
        return first

    async def improve() -> dict:
        llm.log("sweep", f"looking for {[g['fact'] for g in open_facts]}")
        swept = (await sweep(task, await open_tabs(), open_facts, sweep_until)).get("commercials") or []
        if not swept:
            return first
        widened = {**tender, "evidence": (tender.get("evidence") or []) + swept}
        second = await resolvers.commercials(task, widened, mail, others)
        llm.log("sweep", f"commercials decided again with {len(swept)} swept pages")
        return second or first

    job = asyncio.ensure_future(improve())
    waits = {job} | ({asyncio.ensure_future(stop.wait())} if stop else set())
    try:
        await asyncio.wait(waits, timeout=max(1.0, until - time.time() - 5), return_when=asyncio.FIRST_COMPLETED)
        if job.done() and not job.cancelled() and job.exception() is None:
            return job.result()
        if job.done() and job.exception() is not None:
            llm.log("sweep", f"failed: {type(job.exception()).__name__}: {str(job.exception())[:200]}")
        else:
            llm.log("sweep", "stopped: the ERP searches are done, calc goes on with the first answer")
        return first
    finally:
        for waiting in waits:
            waiting.cancel()
