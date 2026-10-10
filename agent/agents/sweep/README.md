# Gap sweep

## Mission

After the first pass, look for the facts it left open on the other websites: on an unseen dataset a record may sit
on another site than the brief suggests. Each open fact gets one short mission; the model chooses where to look.

## Rules

10, 19 (records may be anywhere; nothing may depend on where public-1 keeps them).

## Input / output

- `gaps(tender, requirements, commercials, erp)`: code only, no model → at most `MAX_GAPS` open facts, most important
  first, each `{fact, resolver}`: a tender position the requirements miss, a position without quantity or requirement
  attribute, a setup-pool or bonus member without fee or bands, a position without packaging tariff, no discount
  record, an FX or metal-index key without a rate (once the ERP results are in).
- `sweep(task, tabs, gaps, deadline)`: one `investigate` per open fact and website (tag `sweep:<role>`, at most
  `STEPS` steps); the websites work in parallel, each through the open facts in turn, since two loops on one tab
  would fight over its page → the kept pages per resolver (`requirements` or `commercials`), to decide again.

## Implementation

`agent.py` `gaps`, `mission`, `sweep`. Nothing names a site, a page or a record: the mission states the open fact and
the exact reference only. A tab that fails or runs out of time contributes nothing.

## Pitfalls

- A zero discount is legitimate when no approval exists: the sweep then finds nothing and only costs its time.
- Every mission runs on every website: keep `MAX_GAPS` small and give the sweep its own stage budget.

## Open

- Not wired into `agent.py` `main` yet: it needs a stage budget after the resolvers (Finn's scheduling, I4), then a
  second resolver call with the swept pages. Live S4 (information moved to another site) waits for that.
