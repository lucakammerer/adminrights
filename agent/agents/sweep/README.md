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

- `commercials_with_sweep(task, tender, mail, others, open_tabs, until, stop)`: the commercials resolver, then a sweep
  for the commercial facts it left open, then the resolver again with the swept pages → the commercials answer.

## Implementation

`agent.py` `gaps`, `mission`, `sweep`, `commercials_with_sweep`. Nothing names a site, a page or a record: the mission
states the open fact and the exact reference only. A tab that fails or runs out of time contributes nothing.
`agent/agent.py` `main` runs `commercials_with_sweep` as the commercials job, alongside the ERP searches, on fresh tabs
of the three other websites (idle by then). It only uses free time: no sweep without at least `SWEEP_MIN` seconds
before `until - SECOND_CALL`, and once the ERP searches are done (`stop`) a running sweep or second call is dropped and
the first answer goes to calc. A sweep or second call that fails or finds nothing keeps the first answer. On a run
where commercials leaves nothing open (public-1) it is the commercials call alone.

## Pitfalls

- A zero discount is legitimate when no approval exists: the sweep then finds nothing and only costs its time.
- Every mission runs on every website: keep `MAX_GAPS` small. The sweep only has the time the ERP searches take.

## Open

- Only commercial facts are swept in `main`: an open requirement would need its ERP search again, which the run has
  no time for; such gaps are left to the broadened gathering missions (`common.ALSO_KEEP`).
- Not yet proven live: S4 (`tools/stress/run_agents.py --s4`).
