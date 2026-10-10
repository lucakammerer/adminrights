# Resolvers

`ask_json` calls without a browser: `sites`, `specs`, `requirements`, `commercials`.

## Mission

Assign each website its role, then apply the brief's rules to the kept evidence: which record is valid, what a clause
means. The output is typed facts for `calc`, which does all the arithmetic.

## Rules

- `sites`: 11, 19 (roles judged from the brief, never from site names).
- `requirements`: 1, 2, 13, 14, 17, 20.
- `specs`: the governing-requirement part of `requirements` (the same `GOVERNING` text).
- `commercials`: 5, 12, 16, 21, 22, 23, 24, 25, 26, 28.

## Input / output

- `sites`: brief and the run's websites (id and URL, no logins) → one website per role: `tender_portal`,
  `supplier_portal`, `erp`, `webmail`.
- `specs`: brief, evidence from the supplier portal agent and the technical release mail (as for `requirements`,
  without mail naming a position: it has no tender) → per
  requirement of the current revision `requirement`, `bore_mm`, `stroke_mm`, `pressure_bar`, `mounting`,
  `certification`, `catalogue_group`, `requirement_reasoning`.
- `requirements`: brief, evidence from the tender and supplier portal agents, and the kept mail pages of the technical
  release (the records `common.technical_records` finds in the brief's technical rule, matched by subject or sender,
  `common.mentions`) and mail naming a tender position (`common.names_position`: a clarification kept in the mailbox);
  all kept mail if none matches → per
  position `final_quantity_pieces`, `requirement`, `bore_mm`, `stroke_mm`, `pressure_bar`, `mounting`,
  `certification`, `catalogue_group`, plus `quantity_reasoning` and `requirement_reasoning`.
- `commercials`: brief, evidence from the tender portal and mail agents, plus the pages other websites kept that name
  one of the brief's commercial records (`common.commercial_records`, `common.routed`: an approval or rate message on
  an unexpected site; on public-1 none) →
  - `discount`: `percent`, `min_order_value` (or null), `source`
  - per position: `discount_applies_to` (`base` | `base_and_surcharge` | `none`), `carton_price`,
    `delivery_commitment` (`material_number`, `max_pieces`, `weeks`) or null, `setup_pool_member`,
    `project_bonus_member`, `setup_fee`
  - global: `fx_rates` (EUR per foreign currency unit by FX key), `metal_indices` (EUR/kg on the scenario date),
    `setup_pool_fee`, `project_bonus_bands`

## Implementation

`agent.py` `sites`, `specs`, `requirements`, `commercials`; system prompt `RESOLVE` in `agents/common.py`; `agent/llm.py`
`ask_json` (JSON mode, up to 3 attempts).

- `sites` runs first, while the browsers connect, effort low. The run's submission target is the tender portal; the
  model assigns the other roles (two attempts of at most `SITES_TIMEOUT` seconds each, the second asking only for the
  roles still open; answers that aren't one of the websites are ignored); a role still open gets a remaining website
  by elimination. It never fails the run.
- `specs` runs as soon as the supplier portal and webmail agents are done, effort medium, while the tender agent is
  still working: the ERP searches start from its answer, not from `requirements`. It is skipped when the tender agent
  is done first (or no specification was kept): `requirements` then starts at once and a second call would only
  compete with it. Its governing-requirement text
  (`GOVERNING`) and value schema (`SPEC_JSON`) are the ones `requirements` uses, so both decide the same values.
- `requirements` runs after phase 1, effort medium, alongside the ERP searches; `agent.main` matches its positions to
  the searches by their values and searches the values `specs` missed. Without an answer from `specs` it is on the
  critical path again: the ERP agents wait for it. It asks twice at once and takes the first answer (`first`), because
  one hosted call in a few hangs until its timeout. It gets only the technical mail because all mail doubles its time
  (66 s instead of 34 s on public-1). Prompt: tender quantity replaced by the latest dated clarification, a withdrawn
  answer as if never given (an older change it replaced applies again), sets into pieces; decided from the kept
  pages, not the agents' summaries; the current revision's requirement plus only the amendments naming exactly that
  revision and requirement; a usable stroke plus 2 × the reserve from the latest technical release.
- `commercials` starts with `requirements` and runs alongside the ERP phase (through `sweep.commercials_with_sweep`,
  which looks for facts it left open), effort medium; only `calc.facts` waits
  for it. Prompt: exact reference, authorized sender, latest record up to the scenario date, newer replaces older,
  future-dated records never apply; without a condition group, `base` applies. Every amount is a plain JSON number.

## Pitfalls

- Look-alike references (e.g. the reference with a suffix), superseded and future-dated records sit next to the
  valid ones in the mailbox and the Q&A. The prompts name each of these rules; the `*_reasoning` and `source` fields in the log show
  which record was taken.
- Number formats differ per record. `commercials` returns plain numbers; ERP prices stay "as shown" for `calc.number`.

## Open

- Each resolver is a single model call: a mistake hits many fields at once. The reasoning fields in the log are the
  first place to debug.
- A foreign-currency price whose FX key matches no rate is priced 1:1, a mass without an index adds no surcharge;
  both show as `MISSING` in the calc trace. The key match itself is tolerant (`calc.lookup`).
