# Submit agent

## Mission

Enter the calculated bid in the tender portal's configurator, sign it with a TAN from the mailbox and submit it
bindingly. Without a submission the run scores 0.

## Rules

8, 9, 18 and the brief's "Submission" section.

## Input / output

- Input: answer and `omitted` positions from `calc.compute`, specification per position (for the configurator choices), own mailbox address
  from the mail agent (contact field), portal login, the mail tab for the TAN.
- Output `{confirmation}`: what the portal confirmed.

## Implementation

- `agent.py` `run` → `llm.investigate`, tag `submit`, at most 70 steps, deadline end − 20 s.
  Values in German format with two decimals (`german`). Whole form pages in one `form` call.
- Extra tool `get_tan`: starts its own `investigate` in the mail tab, tag `tan`, at most 12 steps, at most 2 min.
  Finds the newest TAN mail for the request just made.
- Fixed guardrails in the mission: no extra positions, none skipped except the `omitted` ones (omit option in the form), never tick our own terms, request the TAN exactly
  once (a new request invalidates the old one, valid 5 min), net not gross.

## Pitfalls

- Positions appear in any order; check on every page which one it is.
- Forms with a reset button first: click the intended button instead of pressing Enter.

## Open

- Unfinished positions are omitted, but there is no watchdog yet: if the submit agent itself runs short of time, it
  doesn't sign what it has entered so far.
- Locally the submission alone takes about 275 s. In the first full local run it started around end − 6 min, ran out
  of time after 32 steps and submitted nothing.
