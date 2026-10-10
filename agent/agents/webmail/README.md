# Webmail agent

## Mission

Keep every message in the sales mailbox that the rules need for this exact reference, in inbox and archive. Keep
superseded and conditional approvals too, so the resolver can choose the valid one.

## Rules

Gathers for 5, 12, 16, 20, 21, 22, 23, 24, 25, 26, 28. The topics come from the brief (rule 21 names subjects and
senders), read at run time by `common.mail_records`, not from public-1.

## Input / output

- Input: brief, mailbox login.
- Output `RESULT`: `kept` (one line on what was kept), `own_address` (the mailbox's own address, for the contact
  field in the configurator), `other_relevant_facts`, plus `evidence`. The actual content is the evidence.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `webmail`, at most 60 steps, phase 1 deadline.
`wanted` lists the records this run's brief names, from `common.mail_records`: subject/sender pairs, senders named
as `localpart@` with the subject the same sentence gives, and records with only a sender and a meaning (the discount
approval). Nothing is typed into the mission; when the parser finds nothing, the mission tells the model to derive
the records from the brief's rules. The model first searches the reference alone in each folder, then the reference
plus one word of each subject still missing (mail search combines words with AND, as the brief says). Keeps each message via its own URL so sender,
date and body are complete. Skips TAN mails; `get_tan` fetches those ([submit](../submit/README.md)).

## Pitfalls

- Look-alike approvals for other tenders with similar references.
- Superseded approvals, archive folder, paging.

## Open

- The parser reads the brief's English sentence shapes (lists of `Subject/sender`, `localpart@` mentions). A brief
  worded very differently yields fewer records; the mission then falls back to the rules, and the reference-alone
  search still finds every record for the reference.
