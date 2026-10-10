# Tender portal agent

## Mission

Find the tender with the exact reference from the brief in the tender portal and keep everything the rules need from
the portal: the bill of quantities and every bidder Q&A, kept word for word as evidence. It does not start the bid
submission.

## Rules

Gathers for 1, 12, 13, 14, 17, 23, 24, 25 (quantity, condition group, withdrawals, technical amendments, units,
packaging tariff, delivery commitment, setup pool). Decisions happen in [resolvers](../resolvers/README.md).

## Input / output

- Input: brief (up to "## Site access"), portal login, reference taken from the brief by regex.
- Output `RESULT`: `tender_reference`, `title`, `positions[]` (`position`, `description`, `quantity`, `unit`),
  `clarifications[]` (`number`, `date`, `evidence`: the number it is kept as), `other_relevant_facts`, plus `evidence`.
  The Q&A text reaches the resolvers only through the kept pages: copying it into `finish` cost output tokens and
  made the agent reopen pages whose reads had been shortened.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `tender-portal`, at most 45 steps, phase 1 deadline.
Registers interest ("Teilnahme bekunden") if documents are behind it. Keeps the bill of quantities and every Q&A page
with `save_evidence`.

## Pitfalls

- Cookie wall, flaky error pages, documents behind an expression of interest, iframes, ZIPs.
- Q&A spread over several pages; answers change quantities, withdraw earlier ones or assign keys.
- Deadline in another time zone.

## Open

- Only searches the tender portal. If the private dataset puts Q&A elsewhere, they are missed.
