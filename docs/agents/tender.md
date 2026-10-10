# Tender agent

## Mission

Find the tender with the exact reference from the brief in the tender portal and keep everything the rules need from
the portal: the bill of quantities and every bidder Q&A word for word. It does not start the bid submission.

## Rules

Gathers for 1, 12, 13, 14, 17, 23, 24, 25 (quantity, condition group, withdrawals, technical amendments, units,
packaging tariff, delivery commitment, setup pool). Decisions happen in [resolvers.md](resolvers.md).

## Input / output

- Input: brief (up to "## Site access"), portal login, reference taken from the brief by regex.
- Output `TENDER_RESULT`: `tender_reference`, `title`, `positions[]` (`position`, `description`, `quantity`, `unit`),
  `clarifications[]` (`number`, `date`, `question`, `answer`), `other_relevant_facts`, plus `evidence`.

## Implementation

`agent/agent.py` `run_tender` → `llm.investigate`, tag `tender`, at most 45 steps, phase 1 deadline.
Registers interest ("Teilnahme bekunden") if documents are behind it. Keeps the bill of quantities and every Q&A page
with `save_evidence`.

## Pitfalls

- Cookie wall, flaky error pages, documents behind an expression of interest, iframes, ZIPs.
- Q&A spread over several pages; answers change quantities, withdraw earlier ones or assign keys.
- Deadline in another time zone.

## Open

- In the first full local run `finish` came back as a string with invalid JSON (verbatim Q&A text). `investigate`
  wraps it as `{"text": ...}`, so `build_facts` sees no `tender_reference` and the answer's reference is empty.
  Fix: take the reference from the brief and send a broken `finish` back to the model.
- Only searches the tender portal. If the private dataset puts Q&A elsewhere, they are missed.
