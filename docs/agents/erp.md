# ERP agents

Three parts: warm up the login, find the material per requirement, read the facts from the evidence.

## Mission

For every distinct requirement, find the active material whose bore, stroke, pressure, mounting and certification
match exactly, and keep every page holding its facts. If there is none, report that with a reason.

## Rules

3, 4, 6, 10, 15, 22, 23, 25 (material, price condition, lead times, stock, currency, carton size, masses).

## Input / output

- `run_erp_login`: login, output `{ok}`.
- `run_erp_position`: input is one requirement from `resolve_requirements` (5 attributes + `catalogue_group`).
  Agent output `{material_number, why}`.
- `extract_erp`: turns that into `ERP_RESULT`: status, attributes, `available_stock_pieces` (unrestricted only),
  stock and production lead times, `pieces_per_carton`, `allocation_mass`, `surcharge_mass`, `price_index_key`,
  `setup_fee`, `price_condition` (validity, currency, FX key, price unit, number format, scales as shown).

## Implementation

- `agent/agent.py` `run_erp_login`: tag `erp-login`, at most 20 steps, phase 1. Only warms up the session.
- `agent/agent.py` `run_erp_position`: tag `erp:<catalogue group>`, at most 40 steps, deadline end − 6 min.
  `main` dedupes requirements and runs each in its own tab of the same browser.
- `agent/agent.py` `extract_erp`: runs as `check` on `finish`. One `ask_json` reads the facts **only from the kept
  pages**. If required fields or scale prices are missing, `finish` is refused with a list of what is missing.

## Pitfalls

- SAP-style transaction codes, F4 search help, status codes, short session timeout.
- Empty or over-broad searches list nothing; narrow to at most 20 hits.
- Scale prices are often only in a separate view of the condition; several conditions with validity periods.
- Stock by storage location and stock type; blocked stock doesn't count.

## Open

- "No matching material" and "agent failed" look the same (`material_number` empty). Both lead to `no_bid`. The agent
  has to report the difference so `calc` can omit the position in the second case.
- Waits for phase 2 although it only needs the requirements.
