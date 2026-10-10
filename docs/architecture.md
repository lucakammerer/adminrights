# Architecture

Models gather and decide, code calculates. One run in `agent/agent.py` `main`:

```
main (budget = min(time left, 19 min), end = start + budget)
 ├─ Phase 1, parallel, one browser each, deadline end − 9 min
 │   tender · spec · mail · erp-login
 ├─ Phase 2, parallel, no browser
 │   resolve_requirements · resolve_commercials
 ├─ Phase 3, parallel in ERP tabs, deadline end − 6 min
 │   run_erp_position per distinct requirement
 ├─ Phase 4, code
 │   build_facts → calc.compute
 └─ Phase 5, deadline end − 20 s
     run_submit (+ get_tan in the mail tab)
```

With fewer than 4 browsers, `main` opens the remaining sites as tabs in browser 1.

## The tool loop (`agent/llm.py` `investigate`)

Every browser agent is the same loop. Agents differ only in mission, result schema, deadline and `max_steps`.

- **View:** `Tab.read` returns the page as text (`agent/reader.js`): hidden decoys removed; labels, tooltips,
  collapsed details and same-origin iframes included; every control as `[n:kind "label"]`. At most 14,000 characters
  per read, the rest via `offset`.
- **Tools:** `read`, `goto`, `click`, `fill`, `select`, `check`, `press`, `back`, `form` (a whole form page by
  visible labels), `fetch` (read a URL without navigating; opens PDFs and ZIPs), `save_evidence`, `note`, `finish`.
- **Evidence:** `save_evidence` keeps a page word for word. Only this evidence reaches the resolvers and `extract_erp`.
- **Small context:** tool results of the last 4 steps stay in full (`KEEP_STEPS`); older ones are cut to 300
  characters. Whatever the agent wants to keep, it pins with `note`.
- **`check`:** optional validator on `finish`. If it reports a problem, `finish` is refused and the agent keeps
  working (used by the ERP agent).
- **Time:** 60 s before the deadline the agent is told to finish now; after that `finish` is forced via `tool_choice`.
- **Model:** `AGENT_MODEL`, default Qwen3.8-Flash-Next via `QWEN_BASE_URL`. `chat` retries up to 6 times.

The shared system prompt `SYSTEM` in `agent/agent.py` describes the websites' traps in general terms: cookie walls,
popups with a misleading "continue", fake toolbars, unlock sliders, outdated versions first, paging, 503s, number
formats. It names no site and no value.

## Resolvers (`agent/llm.py` `ask_json`)

One call with `response_format=json_object`, up to 3 attempts on invalid JSON. Input is the brief plus the agents'
evidence; output is a fixed JSON schema stated in the prompt.

## Logs

`main` prints one line per phase: `[tender]`, `[spec]`, `[mail]`, `[requirements]`, `[commercials]`, `[erp]`,
`[facts]`, `[calc]`, `[answer]`, `[submit]`. Every agent step appears as `[tag] n: tool {args}`.

## Timing

The first full local run took 1088 s and never submitted: phase 1 ran to its deadline, the ERP phase to end − 6 min,
and the submit agent (about 275 s on its own) ran out of time. Phases wait for each other although the ERP search only
needs the spec result. Lines carry no timestamps yet, so per-phase times have to be inferred.
