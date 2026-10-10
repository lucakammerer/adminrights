"""ERP agents: login, the material per requirement, its facts read from kept pages. See README.md."""
import json

import llm
from agents.common import BOOL, INT, NUM, RESOLVE, STR, SYSTEM, arr, context, login_line, obj, site


RESULT = obj(
    material_number=STR, why=STR, status=STR, description=STR,
    bore_mm=NUM, stroke_mm=NUM, pressure_bar=NUM, mounting=STR, certification=STR,
    available_stock_pieces=NUM, lead_time_stock_weeks=INT, lead_time_production_weeks=INT,
    pieces_per_carton=NUM, allocation_mass=STR, surcharge_mass=STR, price_index_key=STR, setup_fee=STR,
    price_condition=obj(valid_from=STR, valid_to=STR, currency=STR, fx_key=STR, price_unit_pieces=NUM,
                        number_format=STR, scales=arr(obj(from_quantity=NUM, price_as_shown=STR))),
    other_relevant_facts=STR)
REQUIRED = ("material_number", "available_stock_pieces", "lead_time_stock_weeks", "lead_time_production_weeks",
              "pieces_per_carton", "allocation_mass", "surcharge_mass", "price_condition")


async def login(task, tab, deadline):
    mission = f"""{login_line(site(task, tab.site['siteId']))}
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
    data = await llm.ask_json(RESOLVE, question)
    data["material_number"] = data.get("material_number") or chosen["material_number"]
    pc = data.get("price_condition") or {}
    missing = [f for f in REQUIRED if data.get(f) in (None, "", [], {})]
    if not pc.get("scales") or any(s.get("price_as_shown") in (None, "") for s in pc.get("scales") or []):
        missing.append("price scales of the valid condition record")
    if not missing:
        return data, ""
    return data, ("Not done: the kept pages do not show " + ", ".join(missing) + f" for {data['material_number']}. "
                  "Open the pages that show them (for prices: the quantity-scale view of the condition record valid "
                  "on the scenario date), keep them with save_evidence, then call finish again.")


async def run(task, tab, requirement: dict, deadline):
    mission = f"""{context(task)}

{login_line(site(task, 'erp'))} (you should already be logged in)
Your part: find the material for one requirement in this ERP. Requirement: {json.dumps(requirement, ensure_ascii=False)}
1. Search the catalogue group (Kataloggruppe) and read every result page.
2. Compare each candidate's bore, stroke, pressure, mounting and certification with the requirement: all must be
   exactly equal. The material must be active/released (not blocked/gesperrt). If you checked every candidate
   and none qualifies, finish with material_number empty, no_match true and say why.
3. For the chosen material, keep with save_evidence every page that shows its facts: its description (pieces per
   carton, allocation mass, surcharge mass, price index key), technical data, status and lead times (from stock and
   production), the stock detail by storage location / stock type, and the price condition valid on the scenario
   date including its quantity-scale prices (prices may only be on a separate scales view).
Finish with material_number and why; the facts are read from the pages you kept."""
    pages: list[str] = []

    async def check(result, evidence):
        pages[:] = evidence
        return await extract(task, requirement, result, evidence)

    result = await llm.investigate(tab, SYSTEM, mission, obj(material_number=STR, no_match=BOOL, why=STR), deadline,
                                   f"erp:{requirement.get('catalogue_group')}", max_steps=40, check=check)
    if result.get("material_number") and not result.get("price_condition"):
        result, _ = await extract(task, requirement, result, result.get("evidence", []))
    return result
