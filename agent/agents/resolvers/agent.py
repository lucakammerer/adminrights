"""Resolvers: apply the brief's rules to the kept evidence, without a browser. See README.md."""
import llm
from agents.common import RESOLVE, context, evidence


async def requirements(task, tender, spec, mail) -> dict:
    technical = {"evidence": [page for page in mail.get("evidence", []) if "technik" in page.lower()]}
    question = f"""{context(task)}

Evidence from the tender portal:
{evidence(tender)}

Evidence from the supplier portal:
{evidence(spec)}

Technical releases from the mailbox:
{evidence(technical)}

For every tender position, work out:
- final_quantity_pieces: tender quantity, replaced by the latest dated clarification that changes it (ignore
  withdrawn answers), converted to pieces with the governing revision's pieces per set when the unit is a set;
- the governing requirement: the current revision's requirement, with the latest applicable scoped technical
  amendments (only those naming that revision and requirement, only the named attributes); if the stroke is a usable
  stroke, add twice the per-end reserve of its key from the latest technical release for that revision to get the
  nominal stroke.
JSON: {{"positions": [{{"position": "...", "final_quantity_pieces": 0, "quantity_reasoning": "...",
"requirement": "the requirement id the position refers to", "bore_mm": 0, "stroke_mm": 0, "pressure_bar": 0, "mounting": "...", "certification": "...",
"catalogue_group": "...", "requirement_reasoning": "..."}}]}}"""
    return await llm.ask_json(RESOLVE, question)


async def commercials(task, tender, mail) -> dict:
    question = f"""{context(task)}

Evidence from the tender portal:
{evidence(tender)}

Messages from the sales mailbox:
{evidence(mail)}

Resolve, by the brief's rules (exact reference, authorized sender, latest record no later than the scenario date,
newer replaces older, future-dated records never apply):
- discount: the latest director approval for this exact reference: percent and, if it is conditional, its minimum
  undiscounted net order value (else null);
- per position: which Konditionsgruppe applies and therefore whether the discount applies to "base",
  "base_and_surcharge" or "none" (no group: "base"); the packaging tariff in EUR per carton; the delivery commitment
  assigned to it (material number, max pooled pieces, weeks) or null; whether it is a setup-pool member; whether it
  is a project-bonus member; any ordinary setup fee in EUR stated for it (else 0);
- fx_rates: EUR per one unit of each foreign currency, by FX key; metal_indices: EUR per kg by index key, the rate
  valid on the scenario date; setup_pool_fee in EUR; project_bonus_bands as marginal bands.
JSON: {{"tender_reference": "the exact reference", "discount": {{"percent": 0, "min_order_value": null, "source": "..."}},
"positions": [{{"position": "...", "discount_applies_to": "base", "carton_price": 0,
"delivery_commitment": {{"material_number": "...", "max_pieces": 0, "weeks": 0}} or null,
"setup_pool_member": false, "project_bonus_member": false, "setup_fee": 0, "reasoning": "..."}}],
"fx_rates": {{}}, "metal_indices": {{}}, "setup_pool_fee": 0, "project_bonus_bands": [{{"from": 0, "to": null,
"percent": 0}}]}}"""
    return await llm.ask_json(RESOLVE, question)
