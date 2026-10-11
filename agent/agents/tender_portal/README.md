# Tender portal agent

## Mission

Find the tender with the exact reference from the brief in the tender portal and keep everything the rules need from
the portal: the bill of quantities and every bidder Q&A, kept word for word as evidence. It does not start the bid
submission.

## Rules

Gathers for 1, 12, 13, 14, 17, 23, 24, 25 (quantity, condition group, withdrawals, technical amendments, units,
packaging tariff, delivery commitment, setup pool). Decisions happen in [resolvers](../resolvers/README.md).

## Input / output

- Input: brief (up to "## Site access"), portal login, reference from `common.reference` (the brief's first
  identifier in parentheses; then one behind a short label word, with letters and a separator; a bare number such as
  a year only if there is no other).
- Output `RESULT`: `tender_reference`, `title`, `positions[]` (`position`, `description`: a few words and the
  requirement it refers to, the kept page has the full text, `quantity`, `unit`),
  `clarifications[]` (`number`, `date`, `evidence`: the number it is kept as), `other_relevant_facts`, plus `evidence`.
  The Q&A text reaches the resolvers only through the kept pages: copying it into `finish` cost output tokens and
  made the agent reopen pages whose reads had been shortened.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `tender-portal`, at most 45 steps, phase 1 deadline.
Registers interest (the step the brief's Submission section names) if documents are behind it. Keeps the bill of
quantities and every Q&A page with `save_evidence`. The mission
ends with `common.ALSO_KEEP` (keep any other record the rules need on a page opened anyway, never browse for one, finish
when the part is done: the private sites may split the information differently) and, except in the mailbox, `common.NOT_HERE` (finish early when the site doesn't hold the
part's records).

## Pitfalls

- Cookie wall, flaky error pages, documents behind an expression of interest, iframes, ZIPs.
- Q&A spread over several pages; answers change quantities, withdraw earlier ones or assign keys.
- Deadline in another time zone.

## Open

- Only searches the tender portal; Q&A kept by another agent on another site still reach the resolvers
  (`common.ALSO_KEEP`, routing in [resolvers](../resolvers/README.md)).
