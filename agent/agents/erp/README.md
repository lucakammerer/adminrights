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
  Agent output `{material_number, no_match, why, candidates}`. `no_match` is true only after every candidate was
  checked and none qualifies (→ `no_bid`); `candidates` lists each one with the attribute that differs (`differs_in`)
  or `blocked`. An empty result without `no_match` means the search didn't finish (→ position omitted).
- `extract`: turns that into `RESULT`: status, attributes, `available_stock_pieces` (unrestricted only),
  stock and production lead times, `pieces_per_carton`, `allocation_mass`, `surcharge_mass`, `price_index_key`,
  `setup_fee`, `price_condition` (validity, currency, FX key, price unit, number format, scales as shown).

## Implementation

- `agent.py` `login`: tag `erp-login`, at most 20 steps, phase 1. Only warms up the session.
- `agent.py` `run`: tag `erp:<catalogue group>`, at most 40 steps, deadline end − 6 min.
  `main` dedupes requirements and runs each in its own tab of the same browser.
- `agent.py` `run`: at most `PARALLEL` (6) searches at once (`slots`), so a scenario with many requirements doesn't
  crowd the shared model calls; a waiting search keeps its own deadline.
- `agent.py` `extract`: runs as `check` on `finish`. One `ask_json` (effort low: 13 s instead of 56 s; thinking off rewrote number formats) reads the facts **only from the kept
  pages**. If `REQUIRED` facts or scale prices are missing, `finish` is refused with a list of what is missing; the `WANTED`
  facts only some rules use (carton size, allocation and surcharge mass) are asked for once, since a material may
  have none.
- `agent.py` `run`: the search steps end `FINISH_GRACE` (30 s) before the deadline and a forced finish by the deadline,
  so a search cut at its deadline still gets its kept pages read by `extract` before the stage cut (end − 6 min). If
  that read fails, the material and its kept pages still count.
- `agent/agent.py` `erp_search`: a `no_match` (it turns into `no_bid`) is confirmed by a second, independent agent in a
  fresh tab when at least 150 s remain before the ERP deadline; if that one finds a material, its result wins.
- `agent.py` `run` `check`, no-match proof (rules 3, 8): a `no_match` finish is refused (`unproven`) when no page was
  kept, no candidate is listed, or a listed candidate is on no kept page; the mission says an empty or over-broad
  search is not "no match". At most `NO_MATCH_REFUSALS` (2) refusals, so it never loops; after that the second agent
  in `main` `erp_search` still confirms it, and `calc.facts` treats a no_match without kept pages as unfinished. `tests/test_erp_no_match.py` plays it with a fake model.
- `agent.py` `run` `check`: after `extract`, `validate.material_mismatch` compares bore, stroke, pressure, mounting and
  certification with the requirement (rule 3). A difference refuses `finish` once per material with the exact
  difference; finishing again with the same material is accepted, so a misread page never loops to the deadline.

## Pitfalls

- Transaction codes, search helps, status codes instead of words, short session timeout.
- Empty or over-broad searches list nothing; narrow to at most 20 hits.
- Scale prices may sit on another view than the condition header; several conditions with validity periods.
- Stock by storage location and stock type; blocked stock doesn't count.

## Open

- Waits for phase 2 although it only needs the requirements.
