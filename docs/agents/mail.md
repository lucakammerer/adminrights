# Mail agent

## Mission

Keep every message in the sales mailbox that the rules need for this exact reference, in inbox and archive. Keep
superseded and conditional approvals too, so the resolver can choose the valid one.

## Rules

Gathers for 5, 12, 16, 20, 21, 22, 23, 24, 25, 26, 28. The topics come from the brief (rule 21 names subjects and
senders), not from public-1.

## Input / output

- Input: brief, mailbox login.
- Output `MAIL_RESULT`: `kept` (one line on what was kept), `own_address` (the mailbox's own address, for the contact
  field in the configurator), `other_relevant_facts`, plus `evidence`. The actual content is the evidence.

## Implementation

`agent/agent.py` `run_mail` → `llm.investigate`, tag `mail`, at most 60 steps, phase 1 deadline.
Always searches "reference + one topic word", because search combines words with AND. Keeps each message via its own
URL so sender, date and body are complete. Skips TAN mails; `get_tan` fetches those ([submit.md](submit.md)).

## Pitfalls

- Look-alike approvals for other tenders, e.g. the reference with a suffix.
- Superseded approvals, archive folder, paging.

## Open

- The topic list is fixed in the mission. If the private brief changes subjects or senders, the list must be derived
  from the brief.
