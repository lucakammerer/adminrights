# ERP agents

Three parts: warm up the login, find the material per requirement, read the facts from the evidence.

## Mission

For every distinct requirement, find the active material whose bore, stroke, pressure, mounting and certification
match exactly, and keep every page holding its facts. If there is none, report that with a reason.

## Rules

3, 4, 6, 10, 15, 22, 23, 25 (material, price condition, lead times, stock, currency, carton size, masses).

## Input / output

- `login`: login, output `{ok}`.
- `run`: input is one requirement from `resolvers.requirements` (5 attributes + `catalogue_group`).
  Agent output `{material_number, no_match, why}`. `no_match` is true only after every candidate was checked and
  none qualifies (→ `no_bid`); an empty result without it means the search didn't finish (→ position omitted).
- `extract`: turns that into `RESULT`: status, attributes, `available_stock_pieces` (unrestricted only),
  stock and production lead times, `pieces_per_carton`, `allocation_mass`, `surcharge_mass`, `price_index_key`,
  `setup_fee`, `price_condition` (validity, currency, FX key, price unit, number format, scales as shown).

## Implementation

- `agent.py` `login`: tag `erp-login`, at most 20 steps, phase 1. Only warms up the session.
- `agent.py` `run`: tag `erp:<catalogue group>`, at most 40 steps, deadline end − 6 min.
  `main` dedupes requirements and runs each in its own tab of the same browser.
- `agent.py` `extract`: runs as `check` on `finish`. One `ask_json` (effort low: 13 s instead of 56 s; thinking off rewrote number formats) reads the facts **only from the kept
  pages**. If required fields or scale prices are missing, `finish` is refused with a list of what is missing.
- `agent/agent.py` `erp_search`: a `no_match` (it turns into `no_bid`) is confirmed by a second, independent agent in a
  fresh tab when at least 150 s remain before the ERP deadline; if that one finds a material, its result wins.
- `agent.py` `run` `check`: after `extract`, `validate.material_mismatch` compares bore, stroke, pressure, mounting and
  certification with the requirement (rule 3). A difference refuses `finish` once per material with the exact
  difference; finishing again with the same material is accepted, so a misread page never loops to the deadline.

## Pitfalls

- SAP-style transaction codes, F4 search help, status codes, short session timeout.
- Empty or over-broad searches list nothing; narrow to at most 20 hits.
- Scale prices are often only in a separate view of the condition; several conditions with validity periods.
- Stock by storage location and stock type; blocked stock doesn't count.

## Open

- Waits for phase 2 although it only needs the requirements.
