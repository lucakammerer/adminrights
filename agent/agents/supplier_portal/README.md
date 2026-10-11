# Supplier portal agent

## Mission

Find the buyer's technical specification in the supplier portal, determine the revision marked current (not the one
that opens first) and keep every requirement of that revision in full.

## Rules

Gathers for 2, 3, 17, 20 (current revision, attributes for material matching, pieces per set, usable stroke).

## Input / output

- Input: brief, portal login.
- Output `RESULT`: `document`, `current_revision`, `revisions[]` (`revision`, `date`, `status`),
  `requirements[]` (`requirement`, `position`, `bore_mm`, `stroke_mm`, `pressure_bar`, `mounting`, `certification`,
  `catalogue_group`), `other_relevant_facts`, plus `evidence`.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `supplier-portal`, at most 40 steps, phase 1 deadline.
A requirement's wording (a usable stroke with a reserve key, pieces per set) reaches the resolvers only through the kept
pages: copying it into `finish` made the finish the agent's slowest step (1,700 output tokens, 7 s). The mission
ends with `common.ALSO_KEEP` (keep any other record the rules need on a page opened anyway, never browse for one, finish
when the part is done: the private sites may split the information differently) and, except in the mailbox, `common.NOT_HERE` (finish early when the site doesn't hold the
part's records).

## Pitfalls

- Opens the oldest revision first.
- Nested document viewers, requirement tables spread over pages.

## Open

- The ERP search waits for both resolvers but only needs this result plus amendments from the Q&A. Starting it
  earlier saves time.
