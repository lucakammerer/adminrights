# Webmail agent

## Mission

Keep every message in the sales mailbox that the rules need for this exact reference, in inbox and archive. Keep
superseded and conditional approvals too, so the resolver can choose the valid one.

## Rules

Gathers for 5, 12, 16, 20, 21, 22, 23, 24, 25, 26, 28. The topics come from the brief (rule 21 names subjects and
senders), not from public-1.

## Input / output

- Input: brief, mailbox login.
- Output `RESULT`: `kept` (one line on what was kept), `own_address` (the mailbox's own address, for the contact
  field in the configurator), `other_relevant_facts`, plus `evidence`. The actual content is the evidence.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `webmail`, at most 60 steps, phase 1 deadline.
First searches the reference alone in each folder, then the reference plus one word of the subject the brief
authorizes for each record kind still missing (mail search combines words with AND, as the brief says). The discount
approval is identified by the sender the brief names and its meaning, never by a subject typed into the mission. Keeps each message via its own URL so sender,
date and body are complete. Skips TAN mails; `get_tan` fetches those ([submit](../submit/README.md)).

## Pitfalls

- Look-alike approvals for other tenders with similar references.
- Superseded approvals, archive folder, paging.

## Open

- I12 will turn the brief-driven selection into a structured parser, so the resolver can receive the same record
  identifiers without relying on wording in kept pages.
