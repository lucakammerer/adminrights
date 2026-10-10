# Resolvers

Two `ask_json` calls without a browser, in parallel after phase 1. They apply the rules to the evidence and return
typed facts for `calc`. This is where interpretation happens: which record is valid, what a clause means.

## requirements

**Rules:** 1, 2, 13, 14, 17, 20.

**Input:** brief, evidence from tender and spec, and only the kept mail pages that mention a technical release
("technik"), to keep the call small. It is on the critical path: the ERP agents wait for it.

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

**Input:** brief, evidence from tender and mail.

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

`agent.py` `requirements`, `commercials`; system prompt `RESOLVE` in `agents/common.py`. `agent/llm.py` `ask_json`:
JSON mode, up to 3 attempts.

## Open

- Both depend on a single model call. A mistake here hits many fields at once. The `*_reasoning` fields in the logs
  are the first place to debug.
- `calc.facts` falls back to the only available value when an FX or metal index key doesn't match. With several
  indices that can assign the wrong one.
