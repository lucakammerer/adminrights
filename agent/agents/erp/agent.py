"""ERP agents: login, the material per requirement, its facts read from kept pages. See README.md."""
import json

import llm
from agents.common import BOOL, INT, NUM, RESOLVE, STR, SYSTEM, arr, context, login_line, obj
from validate import material_mismatch


RESULT = obj(
    material_number=STR, why=STR, status=STR, description=STR,
    bore_mm=NUM, stroke_mm=NUM, pressure_bar=NUM, mounting=STR, certification=STR,
    available_stock_pieces=NUM, lead_time_stock_weeks=INT, lead_time_production_weeks=INT,
    pieces_per_carton=NUM, allocation_mass=STR, surcharge_mass=STR, price_index_key=STR, setup_fee=STR,
    price_condition=obj(valid_from=STR, valid_to=STR, currency=STR, fx_key=STR, price_unit_pieces=NUM,
                        number_format=STR, scales=arr(obj(from_quantity=NUM, price_as_shown=STR))),
    other_relevant_facts=STR)
FINISH_GRACE = 30  # seconds for a forced finish, which before ran to the stage cut and left the extract none
REQUIRED = ("material_number", "available_stock_pieces", "lead_time_stock_weeks", "lead_time_production_weeks",
              "pieces_per_carton", "allocation_mass", "surcharge_mass", "price_condition")


async def login(task, tab, deadline):
    mission = f"""{login_line(tab.site)}
Your part: log in to this ERP and get past every cookie, notice or unlock step until you reach its main screen
(where materials can be searched). Then finish with {{"ok": true}}."""
    return await llm.investigate(tab, SYSTEM, mission, obj(ok=BOOL), deadline, "erp-login", max_steps=20)


async def extract(task, requirement: dict, chosen: dict, pages: list[str]) -> tuple[dict, str]:
    """Read the material's facts from the pages the ERP agent kept, never from its memory."""
    if not chosen.get("material_number"):
        return chosen, ""
    question = f"""Scenario date and rules are in this brief:
{task['brief'].split('## Rules')[0]}

Requirement: {json.dumps(requirement, ensure_ascii=False)}
The ERP agent chose material {chosen.get('material_number')} because: {chosen.get('why', '')}

Pages it kept from the ERP:
{chr(10).join(pages)}

Fill this JSON only from those pages, copying values exactly as shown; use null for anything the pages do not show.
available_stock_pieces is the freely usable/unrestricted stock only (not blocked/inspection, not a physical total).
price_condition is the condition record valid on the scenario date (inclusive), with every scale and its price exactly
as shown and the record's own number format and price unit.
{json.dumps(RESULT['properties'], ensure_ascii=False)}"""
    data = await llm.ask_json(RESOLVE, question, effort="low")
    data["material_number"] = data.get("material_number") or chosen["material_number"]
    pc = data.get("price_condition") or {}
    missing = [f for f in REQUIRED if data.get(f) in (None, "", [], {})]
    if not pc.get("scales") or any(s.get("price_as_shown") in (None, "") for s in pc.get("scales") or []):
        missing.append("price scales of the valid condition record")
    if not missing:
        return data, ""
    return data, ("Not done: the kept pages do not show " + ", ".join(missing) + f" for {data['material_number']}. "
                  "Open the pages that show them (for prices: the quantity scales of the condition record valid on "
                  "the scenario date), keep them with save_evidence, then call finish again.")


async def run(task, tab, requirement: dict, deadline):
    mission = f"""{context(task)}

{login_line(tab.site)} (you should already be logged in)
Your part: find the material for one requirement in this ERP. Requirement: {json.dumps(requirement, ensure_ascii=False)}
1. Search by the requirement's catalogue group (the brief says how records are found) and read every result page.
2. Compare each candidate's bore, stroke, pressure, mounting and certification with the requirement: all must be
   exactly equal. The material must be active/released, not blocked (the site may show that in German or as a status
   code). If you checked every candidate and none qualifies, finish with material_number empty, no_match true and say
   why.
3. For the chosen material, keep with save_evidence every page that shows its facts: pieces per carton, allocation
   mass, surcharge mass, price index key, technical data, status, lead times (from stock and production), the stock
   by storage location / stock type, and the price condition valid on the scenario date including its quantity-scale
   prices (they may sit on a different view than the condition's header).
Finish with material_number and why; the facts are read from the pages you kept."""
    pages: list[str] = []
    doubted: set[str] = set()

    async def check(result, evidence):
        pages[:] = evidence
        data, problem = await extract(task, requirement, result, evidence)
        differences = material_mismatch(requirement, data) if data.get("material_number") else []
        if differences and data["material_number"] not in doubted:  # once per material: a re-check that keeps it wins
            doubted.add(data["material_number"])
            return data, (f"Not this material: per the kept pages {data['material_number']} differs from the "
                          f"requirement: {'; '.join(differences)}. Compare every candidate of the catalogue group again "
                          "and choose the one that matches exactly, or finish with no_match if none does.")
        return data, problem

    tag = f"erp:{requirement.get('catalogue_group')}"
    with llm.limits(deadline):  # a forced finish must not eat the time the extract below needs after it
        result = await llm.investigate(tab, SYSTEM, mission, obj(material_number=STR, no_match=BOOL, why=STR),
                                       deadline - FINISH_GRACE, tag, max_steps=40, check=check)
    if result.get("material_number") and not result.get("price_condition"):
        try:
            result, _ = await extract(task, requirement, result, result.get("evidence", []))
        except Exception as error:  # noqa: BLE001  out of time: the material and its kept pages still count
            llm.log(tag, f"extract failed: {type(error).__name__}: {str(error)[:200]}")
    return result
