# Architecture

Models gather and decide, code calculates. Every agent is a folder `agent/agents/<name>/` with its code (`agent.py`)
and its documentation (`README.md`); `agent/agents/common.py` holds what they share. One run in `agent/agent.py`
`main`:

```
main (budget = min(time left, 19 min), end = start + budget)
 ├─ Phase 0: resolvers.sites assigns each website its role from the brief (names and ids differ per dataset)
 ├─ Phase 1, parallel, one browser each, wrap-up at end − 10 min, hard cut 30 s later
 │   tender_portal.run · supplier_portal.run · webmail.run · erp.login
 ├─ Phase 2, no browser, hard cut end − 8 min (one retry with effort low until end − 7 min)
 │   resolvers.requirements (resolvers.commercials starts too, runs alongside phase 3)
 ├─ Phase 3, parallel in ERP tabs, hard cut end − 6 min (unfinished requirements → positions omitted)
 │   erp.run per distinct requirement; then resolvers.commercials, hard cut end − 5.5 min
 ├─ Phase 4, code
 │   calc.facts → calc.compute
 └─ Phase 5, deadline end − 20 s
     submit.run (+ get_tan in the mail tab)
```

With fewer than 4 browsers, `main` opens the remaining sites as tabs in browser 1.

Every phase is cut hard by `safe` in `main`: an agent that overruns or crashes yields an empty result and the run
moves on. Under load the hosted model can take 20–90 s per step; without hard cuts one run spent its whole budget
before the submission and scored 0. Browser steps run with `reasoning_effort` low (`STEP_EFFORT`).

## The tool loop (`agent/llm.py` `investigate`)

Every browser agent is the same loop. Agents differ only in mission, result schema, deadline and `max_steps`.

- **View:** `Tab.read` returns the page as text (`agent/reader.js`): hidden decoys removed; labels, tooltips,
  collapsed details and same-origin iframes included; every control as `[n:kind "label"]`. At most 14,000 characters
  per read, the rest via `offset`.
- **Tools:** `read`, `goto`, `click`, `fill`, `select`, `check`, `press`, `back`, `form` (a whole form page by
  visible labels), `fetch` (read a URL without navigating; opens PDFs and ZIPs), `save_evidence`, `note`, `finish`.
- **Evidence:** `save_evidence` keeps a page word for word. Only this evidence reaches the resolvers and `erp.extract`.
- **Small context:** tool results of the last 4 steps stay in full (`KEEP_STEPS`); older ones are cut to 300
  characters. Whatever the agent wants to keep, it pins with `note`.
- **`finish`:** a result that isn't a JSON object (Qwen sometimes sends a string with broken JSON) is refused while
  more than 30 s remain.
- **`check`:** optional validator on `finish`. If it reports a problem, `finish` is refused and the agent keeps
  working (used by the ERP agent).
- **Time:** 60 s before the deadline the agent is told to finish now; after that `finish` is forced via `tool_choice`.
- **Model:** `AGENT_MODEL`, default Qwen3.8-Flash-Next via `QWEN_BASE_URL`. `chat` retries up to 6 times.

The shared system prompt `SYSTEM` in `agent/agents/common.py` describes the websites' traps in general terms: cookie walls,
popups with a misleading "continue", fake toolbars, unlock sliders, outdated versions first, paging, 503s, number
formats. It names no site and no value.

## Resolvers (`agent/llm.py` `ask_json`)

One call with `response_format=json_object`, up to 3 attempts on invalid JSON. Input is the brief plus the agents'
evidence; output is a fixed JSON schema stated in the prompt.

## Logs

Every line goes through `llm.log` as `[tag  123s] ...` with the seconds since start. `main` prints one line per phase
(`sites`, `tender-portal`, `supplier-portal`, `webmail`, `requirements`, `commercials`, `erp`, `facts`, `calc`, `answer`, `submit`); every agent
step appears as `[tag  123s] n: tool {args}`.

## Timing

Measured per test run in `bench/RUNS.md`: where the time went and which phase lost the points.
