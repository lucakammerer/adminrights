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
  `catalogue_group`, `original_wording`), `other_relevant_facts`, plus `evidence`.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `supplier-portal`, at most 40 steps, phase 1 deadline.
`original_wording` stays verbatim because it may state a usable stroke with a reserve key, or pieces per set.

## Pitfalls

- Opens the oldest revision first.
- Nested document viewers, requirement tables spread over pages.

## Open

- The ERP search waits for both resolvers but only needs this result plus amendments from the Q&A. Starting it
  earlier saves time.
