# Resolvers

`ask_json` calls without a browser. `sites` maps the websites to their roles; `requirements` and `commercials` run
after phase 1, apply the rules to the evidence and return typed facts for `calc`. This is where interpretation happens: which record is valid, what a clause means.

## sites

**Input:** brief and the run's websites (id and URL, no logins). **Output:** one website per role: `tender_portal`,
`supplier_portal`, `erp`, `webmail`. Runs first, while the browsers connect; `main` only addresses websites by role,
because ids and names differ between datasets. Two attempts, then the run fails (no role, no bid).

## requirements

**Rules:** 1, 2, 13, 14, 17, 20.

**Input:** brief, evidence from the tender and supplier portal agents, and the kept mail pages that mention "techn"
(the technical release of rule 21: Technikfreigabe, technik@, technical); all kept mail if none does. It is on the
critical path: the ERP agents wait for it, and all mail doubles its time (66 s instead of 34 s on public-1).

**Output per position:** `final_quantity_pieces` (+ `quantity_reasoning`), `requirement`, `bore_mm`, `stroke_mm`,
`pressure_bar`, `mounting`, `certification`, `catalogue_group` (+ `requirement_reasoning`).

**Logic in the prompt:**
- Quantity: tender quantity, replaced by the latest dated clarification, withdrawn answers ignored, sets into pieces.
- Requirement: current revision, plus only the amendments naming exactly this revision and requirement, only the
  named attributes.
- Usable stroke: add 2 × the reserve from the latest technical release for that revision to the stroke.

## commercials

Runs alongside the ERP phase; only `calc.facts` waits for it.

**Rules:** 5, 12, 16, 21, 22, 23, 24, 25, 26, 28.

**Input:** brief, evidence from the tender portal and mail agents.

**Output:**
- `discount`: `percent`, `min_order_value` (or null), `source`
- per position: `discount_applies_to` (`base` | `base_and_surcharge` | `none`), `carton_price`,
  `delivery_commitment` (`material_number`, `max_pieces`, `weeks`) or null, `setup_pool_member`,
  `project_bonus_member`, `setup_fee`
- global: `fx_rates` (EUR per foreign currency unit by FX key), `metal_indices` (EUR/kg on the scenario date),
  `setup_pool_fee`, `project_bonus_bands`

**Logic in the prompt:** exact reference, authorized sender, latest record up to the scenario date, newer replaces
older, future-dated records never apply. Without a condition group, `base` applies.

## Implementation

`agent.py` `sites`, `requirements`, `commercials`; system prompt `RESOLVE` in `agents/common.py`. Reasoning effort:
`sites` low, `requirements` and `commercials` medium. On public-1, low/medium/default all resolved every field
correctly; medium took 129 s for both, default 238 s. `agent/llm.py` `ask_json`:
JSON mode, up to 3 attempts.

## Open

- Both depend on a single model call. A mistake here hits many fields at once. The `*_reasoning` fields in the logs
  are the first place to debug.
- A foreign-currency price whose FX key matches no rate is priced 1:1 (`calc.lookup` returns nothing). The key
  match itself is tolerant (case, spaces, dashes, one key containing the other).
