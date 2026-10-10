# Plan comparison: Luca's `main` vs our planning branch

> Decision record for the merge, written 2026-10-10 by following [`PLAN_MERGE_PROCEDURE.md`](PLAN_MERGE_PROCEDURE.md).
> Compared: Luca's `main` at `3accb38` (PRs #2–#4: agent docs, reference answer + scorer, the agent) and our branch
> `yazan/planning` (rules reference, implementation plan, scouting notes). Rule IDs refer to [`RULES.md`](RULES.md):
> T0–T4 for platform rules, 1–29 for the brief's bid rules. The merged result is [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
> Like Luca's docs, this file holds **no public-1 values**.

---

## 1. Verdict in one paragraph

**Luca's code becomes the base.** It passes the fair-play audit, its calculator is exact, its two resolver calls got
**every fact right** in a full local run, and its tool loop, tool set and per-agent folders are better than what our
plan described. **What fails is time, and time alone:** in the same run the answer was ready only after 17 minutes,
and it was a wrong **no-bid**, because the ERP agents started after their own deadline and reported "no match" for
searches they never ran. Our plan contributes exactly the missing layers: dependency scheduling with per-stage
budgets, a watchdog, deadline-bounded model calls, and the rule that an unfinished search is never a "no match".
Then robustness for the private dataset (site roles, mail topics from the brief, a gap sweep, strict numbers) and the
tooling (tests, audit, release checklist). Our blackboard, need graph and Conductor are **not** adopted as such;
their effect comes through small additions to hooks his code already has.

---

## 2. Evidence

### 2.1 Tests

His repo has **no automated tests**. `eval/compare.py` scores an answer against `eval/expected.json` with the official
weights; that is the only evaluation tool.

### 2.2 Fair-play audit of the package (`agent/`, 24 files)

- **0 hits** for the 79 scouted literals (references, material numbers, all keys, prices in both number formats,
  logins, receipt numbers, dates, hostnames) and for site paths, key-shaped tokens and API keys (T0.1, T0.2, T0.6).
  One false positive: the starter kit's project name in `pyproject.toml`.
- Navigation is model-directed everywhere (`llm.investigate`); helpers read, fetch, fill and calculate (T0.3, T0.4).
- Browsers: only the CDP ones in the sandbox; local launch only without `CDP_URLS` (T0.8).
- **Overfitting, not cheating:** prompts use UI words seen on the public sites. Most are in the brief (allowed), but
  the mail mission's search word for discount approvals is the public mail subject, which the brief never states. If
  the private mailbox words it differently, the discount (rule 5) and every unit price are at risk.

### 2.3 Calculator, in isolation

`calc.facts` + `calc.compute`, fed the public facts **as the pages show them** (raw price strings with their number
format, masses in grams, price units of 1 and 100, two currencies): **matches the reference answer on every field**
of every position, plus decision, discount and total.

Number parser probes (`calc.number`, `calc.grams_to_kg`):

| Input | Format hint | Result | Problem |
| --- | --- | --- | --- |
| `12,345` | `en-US` | 12345 | — |
| `12,345` | *(none)* | 12.345 | **1000× too small** when the hint is missing |
| `12.345` | *(none)* | 12.345 | ambiguous, guessed instead of refused |
| inline `… (de-DE)` tag | *(none)* | tag ignored | the hint in the cell text is not used |
| `1.375 g/Stück` | — | 0.001375 kg | German thousands separator in grams read as a decimal |

### 2.4 Local run of his agent (unchanged code, dry run)

Run on the scouting sites with the local model proxy and a 19-minute budget. The only change: a wrapper outside his
code replaced the final submit step by writing the answer to a file, so nothing was signed.

| Stage | Done at | What happened |
| --- | --- | --- |
| ERP login | 63 s | fine |
| spec agent | 215 s | correct revision and requirements, but `finish` came back as a **string**: the structured fields were lost (evidence pages survived) |
| mail agent | 218 s | 14 relevant messages kept, inbox and archive |
| tender agent | **728 s** | 128 s **past** its 600 s deadline; **fetched the six Q&A pages 35 times** and probed pages and URLs that don't exist (38 model turns, 64 tool calls) |
| requirements resolver | 799 s | 71 s; **all correct** (quantities incl. withdrawal and set conversion, governing requirements incl. derived strokes, catalogue groups) |
| ERP, 5 positions | 809 s | started **after** their fixed deadline (end − 6 min = 780 s); forced to finish at once; **all five reported `no_match: true`** with reasons like "ran out of time before any search" |
| commercials resolver | 1029 s | **about 300 s for one call**; **all correct** (discount + condition, clauses, tariff, commitments, pool and bonus membership, setup fees, FX, dated metal index, pool fee, bands) |
| calc | 1029 s | `no_match` → **no_bid** |
| submit | — | skipped (dry run); it would have had ~90 s of the ~275 s it needs |

**Score of the answer (`eval/compare.py`): 5 / 100** (only the reference). In a real run: most likely **no answer at
all**, 0 points.

Root causes, in order of impact:

1. **Unfinished = no match:** a forced finish lets the ERP agent claim `no_match`, and `calc` turns that into a
   no-bid for the whole tender (F9, F16).
2. **Fixed stage offsets:** deadlines like "end − 6 min" don't depend on when the stage starts; a late stage gets a
   negative budget (F19).
3. **Phase barriers:** the ERP waited for the slowest phase-1 agent although only the spec result was needed (F3).
4. **Redundant copying:** the tender result schema asks for every Q&A answer word for word, while the pages are
   already kept as evidence; trimmed context makes the agent re-read pages again and again (F17).
5. **One huge resolver call:** the commercials call reads every kept page at once and takes minutes (F18).

### 2.5 Reference answer

His `eval/expected.json` and our oracle (`eval/oracle.py`) were derived independently and **agree on
every field to the cent**. The public answer is confirmed twice; either serves as the test reference.

### 2.6 Code review findings (his code, by file and function)

| # | Where | Finding | Rules | Severity |
| --- | --- | --- | --- | --- |
| F1 | `agent.py` `main`, `agents/erp/agent.py` `run` | Site ids hardcoded; `agents/common.py` `site` raises `StopIteration` if one is missing → crash, no answer, if the private dataset names sites differently | T1.3, T1.12 | **high** |
| F2 | `agent.py` `main` | `task["submission"]` (where the answer goes) is never read | T1.12 | medium |
| F3 | `agent.py` `main` | Phase barriers: ERP waits for all of phase 1 and the requirements resolver; submit starts last | T1.3, T3.2 | **high** (run) |
| F4 | `llm.py` `chat` | 360 s timeout × 6 attempts per call, not bounded by any deadline | T1.3 | **high** |
| F5 | `agents/submit` | No watchdog: what is entered is never signed if time runs short | T1.3, T1.9 | **high** |
| F6 | `agents/resolvers` | All record selection and two calculations (set → pieces, usable → nominal stroke) inside one model call each; correct in the run, but nothing checks it | 1, 2, 5, 12–14, 16, 17, 20–26, 28 | medium (run: correct) |
| F7 | `calc.py` `number`, `grams_to_kg` | Ambiguous numbers guessed without a hint; inline format tags ignored; floats between parsing and `Decimal` | 4, 22 | medium |
| F8 | `calc.py` `facts` | An unmatched FX or index key silently takes the only available value | 22, 28 | medium |
| F9 | `agents/erp` | Material match and `no_match` rest on the agent alone; no code check of attributes and status | 3, 8 | **high** |
| F10 | `agents/mail` | Topics and sender local parts fixed in the mission; one search word comes from a public mail subject | T0.11, 5, 10, 21 | medium |
| F11 | `agents/tender`, `agents/spec` | Each agent searches only "its" site; Q&A or specs elsewhere are missed | 10 | medium |
| F12 | `browser.py` `Tab.settle` | Fixed 1.4 s sleep on every read and action | T3.2 | low |
| F13 | `browser.py` `pdf_text` | `pypdf` is not a dependency: PDFs silently unreadable | 10 | medium |
| F14 | `calc.py` `compute` | Positions without prices are omitted (rule 9 policy) and leave the pooled computations | 9, 15, 16, 25, 26 | low |
| F15 | `llm.py` `investigate` | Two docstrings (the second is dead); `pyproject.toml` still named as the starter kit | T4.6 | cosmetic |
| F16 | `agents/erp` `run`, `calc.compute` | **A forced finish is reported as `no_match`**, which `calc` turns into a no-bid (run: 5 of 5 positions) | 3, 8, 9 | **critical** (run) |
| F17 | `agents/tender` `RESULT` | Asks for every Q&A word for word in `finish`; with trimmed context the agent re-fetches pages (35 fetches of 6 pages) | T3.2 | **high** (run) |
| F18 | `agents/resolvers` `commercials` | One call over all kept pages: ~300 s | T3.2 | high (run) |
| F19 | `agent.py` `main` | Stage deadlines are fixed offsets from the end; a late stage starts with a negative budget | T1.3 | **critical** (run) |
| F20 | `llm.py` `investigate` / `parse_object` | `finish` as a string isn't always recovered: the spec result became `{"text": ...}` | T4.2 | medium (run) |

---

## 3. Point by point

Verdict: **L** = Luca's approach, **O** = ours, **L+O** = his as base with the named part of ours.

| # | Area | Luca | Ours | Verdict | Why |
| --- | --- | --- | --- | --- | --- |
| 1 | Architecture and roster | Phased pipeline; per-site agents (tender, spec, mail, ERP per requirement, submit + TAN helper); 2 resolver calls; code calc | Conductor + need graph + 4 site-agnostic operators + auditor + calc + notary + time keeper | **L+O** | His exists and gets the facts right. Ours costs hours. Take his skeleton; add scheduling, budgets and guards |
| 2 | Coordination | `main` passes dicts between fixed phases | blackboard ledger + event bus | **L+O** | No bus. Replace phase barriers with `asyncio` tasks that start when their inputs exist, each with its own minimum budget (F3, F19) |
| 3 | Model-directed navigation | one generic tool loop; model picks every action | same + decision-id trace | **L** | Equivalent; his step log proves model direction |
| 4 | Page perception | `reader.js`: decoys out, tooltips, details, image labels, iframes, refs, 14k chars + offset | digest with the same rules + chrome suppression, table markers, hidden counts, vision fallback | **L+O** | His reader works on the real sites. Add off-screen/zero-size hiding and `pypdf`; the rest only if a test shows the need |
| 5 | Obstacles | auto-closes in-page dialogs, accepts browser dialogs; the model handles cookies, gates, retries, re-login | code reflexes + `unlock_gate` tool | **L+O** | Keep his. Add code-side retry of transient error pages and auto re-login; adaptive settle instead of the fixed sleep |
| 6 | Extraction | `save_evidence` keeps pages; agents copy values into result schemas | quote-anchored claims, code parses numbers | **L+O** | Keep evidence pages, but stop asking agents to copy what the evidence already holds (F17); decisive values carry a quote; strict number parsing |
| 7 | Record selection | one model call per resolver | candidates extracted, code selects, model pick as second key | **L now, O later** | The run proves his resolvers right on public. Code selection becomes a P2 safety net for the private dataset, not a P1 rewrite |
| 8 | Calculator | `calc.py`, exact (§2.3) | same design + tests | **L+O** | Keep; add tests, `Decimal` throughout, loud failures instead of silent fallbacks |
| 9 | Bid / no-bid | `no_match` → no_bid; unfinished → omitted | presence and absence proofs, auditor sign-off | **O** (inside his hook) | The run produced a false no-bid from timeouts (F16). Unfinished must never be "no match"; no-bid needs code-checked evidence and a confirmation |
| 10 | Submission | one model agent, `form` tool, TAN helper; starts after calc | state machine, pre-fill, code read-back, single final step | **L+O** | Keep his agent; add stage 1 at start (participation, bidder data, offer kind), read-back before the TAN, a watchdog |
| 11 | Time | budget = min(time left, 19 min); fixed phase offsets | deadline ladder, always-submit guarantee | **O** | The run: answer only after 17 min, and wrong because of time |
| 12 | Parallelism | 4 browsers, ERP per requirement in tabs, parallel tool calls | same + worker tabs | **L** | Good; add a concurrency cap well under the team's 32 Qwen calls |
| 13 | LLM strategy | Qwen everywhere, native tool calls, JSON mode, context trimming with `note` | Qwen + optional Clef, caching layout, voting for prose → enum | **L** | Proven. Add deadline-bounded calls (F4); smaller resolver inputs (F18) |
| 14 | Generalization | generic tools and prompts; fixed site ids, information locations and mail topics | site-agnostic operators, routing by profile, key graph | **L+O** | Site roles from the run; mail topics from the brief; a gap sweep for missing facts and unresolved keys |
| 15 | Compliance safeguards | `AGENTS.md` non-negotiables, docs rules | automated audit, package check, Definition of Done | **L+O** | His conventions + our audit (`tools/audit_package.py`) before every submission |
| 16 | Testing | `eval/` scorer + reference; local and test runs | unit tests, recorded pages, mutations, chaos, Mirror World | **L+O** | His scorer replaces our planned one. Add pytest, a dry-run mode that scores itself, recorded-page tests; mutations later |
| 17 | Observability | tagged log lines with seconds; phase dumps; calc trace | JSONL trace, summary, viewer | **L** | Enough; add an end-of-run summary (time per stage, turns per agent) |
| 18 | Code quality | small modules, folder + README per agent, English, docs with code | typed data model, tools/ and tests/ | **L+O** | Keep his structure; add tests and the small fixes in §2.6 |
| 19 | Workflow | `t3/` branches + PRs merged by Luca; Entire checkpoints; submit only after Luca approves | release train, tags, freeze, Definition of Done, best-of-3 | **L+O** | His PR flow + our release discipline; the final run takes the **latest** passed submission |
| 20 | Work split | not defined | 3 roles over 24 h | **O**, re-cut | Around his modules (IMPLEMENTATION_PLAN §14) |
| 21 | Docs layout | `docs/` = what the system *is*; no public-1 values; per-agent READMEs | `docs/` with plans, requirements, scouting values | **L** | Values in `docs/` can leak into prompts through coding agents. Value-laden files move to `eval/`; the two rules files are now one (§6) |

---

## 4. Credit where it's due

**In Luca's code, missing or weaker in our plan (adopted):**

- the generic `investigate` loop with `KEEP_STEPS` trimming and `note` pinning;
- the `form` tool (fill by visible labels, survives reloads), the `fetch` tool (read without navigating, in
  parallel), `save_evidence`;
- the `check` hook that refuses `finish` until required facts are present;
- `safe()` crash isolation per agent;
- resolver prompts that got every rule right on the first full run;
- knowledge from his scouting: the expression-of-interest step, the terms-and-conditions box that must stay
  unticked, the bidder's own address for the contact field, an extra look-alike reference;
- `AGENTS.md` "Ways to hurt yourself"; per-agent READMEs with fixed sections; docs change with code.

**In our plan, missing in his code (to add):**

- per-stage budgets, dependency scheduling, a watchdog and early submission steps;
- "unfinished is never no match" and code-checked presence/absence evidence for the material decision;
- strict number parsing; code-side selection as a cross-check;
- a gap sweep and robust site roles for the private dataset;
- automated audit, unit tests, release discipline, best-of-3.

---

## 5. His code against the hard rules

| Rule | Status | Note |
| --- | --- | --- |
| T0.1 no copied values | ✅ | audit 0 hits |
| T0.2 no site-specific navigation | ✅ | |
| T0.3 / T0.4 model directs, helpers help | ✅ | |
| T0.5 no pre-solved answer in the package | ✅ | `eval/` is outside `agent/` |
| T0.6 / T0.7 proxy only, no outside hosts | ✅ | |
| T0.8 no own browsers in the sandbox | ✅ | |
| T0.11 brief facts read at run time | ⚠️ | mail topics fixed (F10) |
| T1.3 always answer in time | ❌ | dry run: answer at 1029 s, submission would not have fit (F3, F4, F5, F19) |
| T1.4 exact reference | ✅ | |
| T1.5 one submission | ✅ | |
| T1.8 TAN handling | ✅ | |
| T1.12 site roles from the run | ❌ | F1, F2 |
| Bid rules 1–29 | ⚠️ | calc exact; resolvers correct in the run; rule 3 broken by F16 |

---

## 6. The two rules files

Luca's `docs/rules.md` and our previous `docs/RULES.md` are now **one file**, the current [`RULES.md`](RULES.md). What each contributed:

| Aspect | Luca's `rules.md` | Our previous `RULES.md` | In the merged file |
| --- | --- | --- | --- |
| Scope | the 29 bid rules | fair play, run validity, bid rules, rank, craft, traps, Definition of Done | everything, in tiers T0, T1, bid rules, T3, T4 |
| Numbering | the brief's 1–29 (cited by agent READMEs) | own T2.1–T2.17 | **the brief's 1–29** for bid rules; T-IDs for the rest |
| Precision | one line per rule; drops details (price units, "not after the scenario date", "no fallback", available vs physical stock) | formal definitions, `LATEST`, notation | ours, generalized |
| Implementation map | gather / decide / status per rule | none | his, kept current with F/I references |
| Checks | none | per rule | per rule |
| Public-1 values | none | examples and pitfalls with real values | none (his rule) |
| Scoring table | in his `challenge.md` | repeated | linked, not repeated; only its consequences stay |
| Partial submission | omit unfinished positions | omit only unconfigurable ones | ours: an omitted position earns nothing, a submitted one keeps every correct field |
| Ambiguities, traps, Definition of Done | — | yes | yes, plus his traps (fake browser chrome, reset buttons first, instructions inside documents) |
| File name | `rules.md` | `RULES.md` | `RULES.md`; Luca's `rules.md` is removed in the merge (the two names collide on macOS and Windows) |
