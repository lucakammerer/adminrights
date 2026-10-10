"""Gap sweep (I16): code lists the facts the first pass left open; for each, one short mission looks for it on the
other websites, where the model chooses what to open. See README.md."""
import asyncio

import llm
from agents.common import BOOL, STR, SYSTEM, context, login_line, obj
from calc import lookup

SPEC = ("final_quantity_pieces", "bore_mm", "stroke_mm", "pressure_bar", "catalogue_group")
MAX_GAPS = 3  # the most important open facts only: each costs a mission per website
STEPS = 12
RESULT = obj(found=BOOL, fact=STR, where=STR)


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
    return f"""{context(task)}

{login_line(tab.site)} (you may already be logged in)
One fact the bid needs is still open after the first pass: {gap['fact']}.
The brief's rules say where such a record usually is, but this website may hold it instead (a document, a message, a
record, a Q&A answer). Look for it on this website for the exact tender reference only; you choose what to open and
search. Keep every page that states it with save_evidence. If this website does not hold it, finish quickly with
found false. Finish with found, the fact as written and where it is."""


async def sweep(task: dict, tabs: dict, gap_list: list[dict], deadline: float) -> dict[str, list[str]]:
    """One mission per open fact, on every website's tab at once; returns the kept pages per resolver. A tab that
    fails or runs out of time just contributes nothing."""
    pages: dict[str, list[str]] = {}

    async def look(gap, role, tab):
        result = await llm.investigate(tab, SYSTEM, mission(task, tab, gap), RESULT, deadline, f"sweep:{role}",
                                       max_steps=STEPS)
        return gap, result

    jobs = [look(gap, role, tab) for gap in gap_list for role, tab in tabs.items()]
    for outcome in await asyncio.gather(*jobs, return_exceptions=True):
        if isinstance(outcome, BaseException):
            llm.log("sweep", f"failed: {type(outcome).__name__}: {str(outcome)[:200]}")
            continue
        gap, result = outcome
        if result.get("found") and result.get("evidence"):
            pages.setdefault(gap["resolver"], []).extend(result["evidence"])
    return pages
