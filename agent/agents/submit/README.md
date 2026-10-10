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

- `agent.py` `run` → `llm.investigate`, tag `submit`, at most 70 steps, deadline end − 20 s, cut hard at `end`.
  Values in German format with two decimals (`german`). Whole form pages in one `form` call, a configurator's
  dependent choices each followed by its apply button; `form` opens collapsed sections around a field itself.
- One `form` call per position: the mission sends the configurator's choices without reading their options first,
  because `form` picks an option by its exact text, its beginning or any part of it, and a step without a matching
  option stops the call and lists the page's options. Test runs filled the configurator one choice per model call,
  which was most of the submit agent's time. Where a configurator narrows its materials by the earlier choices, a
  wrong choice shows up as a material step without a match; `verify_summary` still checks prices and total.
  Choices are named by field label: refs are `data-aref` attributes written by `read`, so a re-render after an apply
  removes them and a ref step later in the same call fails (one test run chained by ref and fell back to one choice
  per call).
- Watchdog (first slice): `SIGN_BY` = 180 s before the deadline the agent gets its own warning: omit every position
  not completely entered, request the TAN, sign. The generic "call finish now" would end the run unsigned.
- Extra tool `get_tan`: starts its own `investigate` in the mail tab, tag `tan`, at most 12 steps, at most 2 min.
  Finds the newest TAN mail for the request just made. The tab is first opened on the mailbox's start page, and a
  `check` refuses a finish without `found` and a TAN while more than 45 s remain: in one test run the look-up started
  inside the mail agent's last search list, returned the newest message there (not a TAN mail) with no TAN, and the
  second look-up the submit agent then started ran out of time, so nothing was signed.
- Extra tool `verify_summary` (I6b): code reads the summary page and reports every unit price and the total net that
  isn't on it as calculated; the mission calls it before the TAN request. Values the summary doesn't show are fine.
- Fixed guardrails in the mission: no extra positions, none skipped except the `omitted` ones (omit option in the form), never tick our own terms, request the TAN exactly
  once (a new request invalidates the old one, valid 5 min), net not gross.

## Pitfalls

- Positions appear in any order; check on every page which one it is.
- Forms with a reset button first: click the intended button instead of pressing Enter.
- The mail tab is shared with the mail agent: whatever list it left open is not where the TAN message is.

## Open

- The watchdog is a warning to the model, not code: if the model ignores it or the TAN look-up stalls, nothing signs.
- Stage 1 (bidder data, offer type) could run while the ERP agents work (I6).
