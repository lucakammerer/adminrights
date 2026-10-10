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
  field in the configurator), `search_url` (one search it ran, so the TAN look-up searches the same way), `other_relevant_facts`, plus `evidence`. The actual content is the evidence.

## Implementation

`agent.py` `run` → `llm.investigate`, tag `webmail` (`webmail-2`, `webmail-3` for the others), at most 60 steps,
phase 1 deadline. `agent.main` first runs `login` (tag `webmail-login`: three logins at once in one browser expired each
other's form and cost 150 s), then up to `AGENTS` (3) of them at once, each in its own tab with its share of the
records (`groups`): the technical release alone first, since the specification resolver and with it the ERP searches
wait only for that share, then the other records in turns; with fewer records than agents, one agent takes all.
`merge` joins their results (each kept page once). Under load a step took 15-30 s and one agent for every record
took 14-20 steps one after another.
`wanted` lists the records this run's brief names, from `common.mail_records`: subject/sender pairs, senders named
as `localpart@` with the subject the same sentence gives, and records with only a sender and a meaning (the discount
approval). Nothing is typed into the mission; when the parser finds nothing, the mission tells the model to derive
the records from the brief's rules. The model first searches the reference alone in each folder and keeps each
record's message as soon as a result list shows it, via its own URL so sender, date and body are complete; then it
searches the reference plus one word of each subject still missing (mail search combines words with AND, as the
brief says). It never searches a word or sender without the reference, and stops once every record is kept or its
searches came back empty. Skips TAN mails; `get_tan` fetches those ([submit](../submit/README.md)). The mission
ends with `common.ALSO_KEEP` (keep any other record the rules need on a page opened anyway, never browse for one, finish
when the part is done: the private sites may split the information differently) and, except in the mailbox, `common.NOT_HERE` (finish early when the site doesn't hold the
part's records).

## Pitfalls

- Look-alike approvals for other tenders with similar references.
- Superseded approvals, archive folder, paging.

## Open

- The parser reads the brief's English sentence shapes (lists of `Subject/sender`, `localpart@` mentions). A brief
  worded very differently yields fewer records; the mission then falls back to the rules, and the reference-alone
  search still finds every record for the reference.
