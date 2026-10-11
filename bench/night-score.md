# Night loop: score and efficiency (`luca/night-score`)

## Morning summary

Best candidate: **c31d89a** (a4b9d2c + a twin for stuck Qwen calls + the TAN look-up in a new mailbox tab). Its runs:
100 / 11:52 / $0.296 / 210.8 $·s (run_c13fd1a74d3ad98c), 100 / 15:21 / $0.261 / 240 $·s (run_d0283ff8e1a3187d). On
$·s, a4b9d2c's runs are still the best: 156.2 (run_bd99f53d4d7d5c7f) and 181.6 (run_ba99f2d4eb2f586e). Main on Qwen
tonight: 122.6-262 $·s. Our submission: 70 $·s (Haiku). Rank 1: 25 $·s. No Qwen run is a submit candidate on $·s.
Merge to main, each worth it on its own:
- a4b9d2c (calc): the setup fee comes from the commercials; the ERP's per-material fee only when they lack the
  position. Fixed an 84.8 (double count). Judgement call, see iteration 2.
- c31d89a (submit): the TAN look-up opens a new tab of the mailbox (same login). The mail agents' idle tab hung
  45-150 s in 5 of 10 runs, main included; with the change 37 s and 63 s.
- 4d4a37f (llm): a streamed call without its first chunk after 10 s gets a twin. 6-10 calls a run sat silent for 30 s
  before; in run_c13fd1a74d3ad98c 9 twins, each answered in ~2 s, the originals never reached the platform.
- 7cb21db (submit `form` hold): insurance, never fired live.
Distrust: f5e86da (radical-speed merge) is not shown faster on Qwen; load noise dominates single runs. Next loss to
fix: browser pages that stop answering (75-207 s per run, see backlog).

## Iterations

### 1 · 01:50 · Structural speedups of `luca/radical-speed` on Qwen

Hypothesis: on Qwen, wall time is spent in model output (≈45 tok/s, reasoning included) and in serial stages.
`luca/radical-speed` (Luca, not on main) removed serial stages: ERP searches start from the specification, commercials
in three parallel parts, the submission starts early, webmail logs in once and fans out, cache-friendly trimming. It
reached 9–10 min on Haiku. Merge it onto HEAD while Qwen stays the default model and compare with two baseline Qwen
runs of HEAD.

Baseline (HEAD 1fa269f, Qwen): run_c7805bca216fa2e0, run_39d8950d739e2e2a.

Merge db77ee5: `llm.py` and `submit/agent.py` from radical-speed, with Qwen as the default again and the submit
read-back of the breakdown values (939e2d0) restored; `tests/test_chat.py` dropped (the streamed silence check
replaces the twin on Qwen, covered in `test_run_guards`). Gate: green, audit clean. The adversarial reviewer found one
credible reject risk: `paging.py` took a list's row links (`?id=17`) for its pager, so code would open records no
model chose. Fixed in f5e86da: pager links need a short label and numbers that step evenly from the current page;
two tests.

Evidence: both merge runs 100, eligible, 132.8 and 197 $·s against 257.8 and 262 $·s for the baseline. Confounded by
load: queue wait 13 min in the baseline against 26 s in run_364ee0e5b5151237. Paired runs started 00:23 UTC to settle
it: baseline run_52961ce393c136de (1fa269f, from `git archive`), merge run_cf57141fcf4352a0 (f5e86da).

Verdict: kept provisionally (quality held 2/2, faster in both); the paired runs decide. Where the time goes now
(run_364ee0e5b5151237): phase 1 to ~230 s, ERP searches to 448 s (critical path), submit + TAN 448→661 s, 22
sequential submit steps (run_a65e32634be4efce: 314 s).

Next idea: the submit phase. It starts early but enters each configurator position in several form calls after
the bid arrives; time per step is browser waits plus a 5–15 s Qwen call.

Seen on the way: run_0b1441de63cf8acb (package fc98097b, not mine, all Haiku): 100 in 5:09, $0.091, 28.1 $·s.

### 2 · 02:22 · Submit re-entry and a setup-fee double count

Paired runs of iteration 1: main 1fa269f run_52961ce393c136de 100 / 10:01 / 122.6 $·s; merge f5e86da
run_cf57141fcf4352a0 84.8 / 14:46 / 232.9 $·s. The merge's earlier lead was load. The 84.8 was calc, not the merge:
the ERP agent kept a material's planning tab with its own setup fee, and `calc.facts` added it to the commercials'
per-position fee (01.02 got a fee it doesn't have, 01.03 counted it twice). Fixed in a4b9d2c with a test.

Hypothesis (submit): the submit agent loses ~110 s when `verify_summary` finds a breakdown value typed wrong, because
the portal makes it walk back and re-enter every later position (run_a65e32634be4efce: 01.04 bonus typed as 0,
same field wrong in run_c086c4a6429b3bd9). Catch it before the page's next-step button: 7cb21db holds a `form` call
once per position when it types the position's unit price but not one of its non-zero breakdown values; a position
held again switches the hold off (portal asks for them elsewhere). Number parsing accepts any common format.

Gate: check_release green, audit clean. Reviewer on 7cb21db: no hardcoding; asked for a cap on holds and a format-
agnostic parser, both done. Reviewer on a4b9d2c: no hardcoding, warned an unseen dataset might keep the ordinary
setup fee only in the ERP; kept because the old sum double-counts whenever both sources show it, and the ERP value
still stands in when the commercials lack the position. Flagged for Luca above.

Runs (a4b9d2c): run_bd99f53d4d7d5c7f 100 / 11:20 / 156.2 $·s, run_ba99f2d4eb2f586e 100 / 12:52 / 181.6 $·s. Both
signed, setup fees right (01.02 0, 01.03 106.62), `verify_summary` matched first time, the hold never fired (no false
hold, but its catch is untested in a live run). Verdict: keep both; the hold is insurance (saves ~110 s when it
catches), not a measured speed-up.

Next idea: time to the bid varies 350–545 s between identical runs; the ERP phase (one requirement searched late
because it "differs from the early searches") is where it goes. Profile run_ba99f2d4eb2f586e 4–9 min.



### 3 · 03:00 · A twin for a streamed call that brings no first chunk

Profile of run_ba99f2d4eb2f586e (bid only at 545 s): the critical path was the slowest ERP search (189→510 s, 39
steps, forced finish). Three of its gaps were `[llm] retry after APITimeoutError at 30 s`: a hosted Qwen call that
never brought a byte, dropped only at `SILENCE`. Count per run: run_ba99f2d4eb2f586e 6, run_cf57141fcf4352a0 10,
run_bd99f53d4d7d5c7f 0, run_a65e32634be4efce 0. Answered calls' queue wait p95 1.3 s (night) to 14 s (loaded).

Hypothesis: a streamed attempt without its first chunk after 10 s gets a twin (the silent one keeps running, first
answer wins), as OpenRouter calls already do after 15 s. Saves ~20 s per stuck call; costs a twin on queue waits over
10 s under load.

Commit 4d4a37f: `llm.FIRST_CHUNK`, `reply` sets an event at its first chunk, `chat` sends the twin and logs
`[llm] twin after`. Test: a silent first request answered by the twin in < 5 s. Gate: check_release green, audit clean,
reviewer PASS (watch the twin rate under load: it adds requests while the service queues).

Runs (4d4a37f): run_840f0cd20f29dc8c 100 / 11:53 / $0.213 / 151.8 $·s, run_6038f546123323a1 100 / 14:10 / $0.265 /
225.4 $·s. Neither had a stuck call, so the twin never fired: neutral, untested live. Kept (cheap insurance, reviewer
PASS); judge again once a run logs `twin after`.

Both runs lost their time after the bid instead (381→713 s, 415→850 s): browser tabs that stopped answering. A survey
of 8 earlier runs (subagent, run_profile + logs) found every stall over 40 s in the TAN look-up on the mailbox's
original tab: run_bd99f53d4d7d5c7f 75 + 89 s (TAN finish forced), run_52961ce393c136de 75 s, run_a65e32634be4efce
44 s, run_c7805bca216fa2e0 75 s; plus run_840f0cd20f29dc8c 150 s. The pattern: `start page failed: TimeoutError`
(15 s), then the first read waits out `TOOL_TIMEOUT` (60 s); a later look-up gets through at once. 5 of 10 runs.

Change c31d89a: `get_tan` opens a new tab of the mailbox's browser (same login) through `agent.fresh` for each look-up
instead of the mail agents' idle tab. Gate: green, audit clean, reviewer PASS (a mailbox with a per-tab session would
need a new login; the mission carries the login line). Runs (c31d89a): run_c13fd1a74d3ad98c, run_d0283ff8e1a3187d
(started 01:20 UTC). Judge by: time from `get_tan` to the TAN agent's finish, quality, signing.

Results (c31d89a): run_c13fd1a74d3ad98c 100 / 11:52 / $0.296 / 210.8 $·s, run_d0283ff8e1a3187d 100 / 15:21 / $0.261 /
240 $·s. TAN look-up 37 s and 63 s, no stall (was 75-150 s in 5 of 10 runs). The twin fired 9 times in run_c13fd: each
original never shows in the platform's calls (stuck before the model), each twin answered in ~2 s; no 30 s timeout.
Total $·s is not better: phase 1 ran to 446 s in run_d0283ff8e1a3187d and a submit `read` on the tender portal hung
75 s there (as in run_6038f546123323a1: 3 hung tools, 207 s). Verdict: keep both 4d4a37f and c31d89a; their mechanism
is shown, the $·s gain is hidden by load and the next loss, the frozen page.

Next idea: a browser tool that times out means the page stopped answering (TimeoutError after `TOOL_TIMEOUT`, then
`investigate` waits 15 s more on a `tab.read()` of the same page; the model then reads again, another 75 s). Give
`Tab` a way to reopen its current address in a new page of the same browser (handlers re-registered, old page closed
without waiting) and do it in `investigate`'s error path for a timeout, telling the model. Generic web mechanics;
check the submit agent's `form` handler too (its own `wait_for`).

### 4 · 03:36 · Reads of long-idle tabs hang on the settle wait

Evidence: run_d0283ff8e1a3187d: the submit agent's first `read` after the bid (616 s) came back only at 693 s
(60 s `TOOL_TIMEOUT` + 15 s re-read); the tab had idled since the early start. Same shape as the TAN look-up stalls
(mailbox tab idle for minutes) and run_6038f546123323a1 (submit tab, 479→686 s). Every stall was on a tab that sat
unused for minutes.

Hypothesis: `Tab.settle` awaited one in-page Promise that looped on the page's own `setTimeout` (50 ms ticks). A
background tab's timers are throttled (Chrome: once a minute after 5 min hidden), so the promise outlived the tool
timeout. Locally not reproducible: Playwright-launched Chromium keeps every tab visible and disables throttling;
the platform's browsers are attached over CDP, their flags unknown.

Change 3258746: settle polls a synchronous evaluate (ms since the last DOM change, pending short timers) from Python
every 50 ms, each poll bounded, at most `SETTLE_MAX`. Same semantics on a normal page. Test: a page whose timers
never fire (old code hangs to the test's 10 s guard, new one returns in < 2.5 s). Gate: check_release green, audit
clean, reviewer PASS (gap noted: if a tab is truly frozen rather than throttled, the dialog sweep after the loop has
no bound; add one if stalls persist).

Runs (3258746): run_590a955bd423bbac, run_01a5fe851c09aba6 (started 01:50 UTC). Judge by: any `read`/action on an
idle tab taking > 30 s (submit's first read after the bid, `get_tan`), quality, signing.

## Backlog

- Frozen pages (see iteration 3 "Next idea"): 75-207 s per run in run_6038f546123323a1 and run_d0283ff8e1a3187d,
  both on the submit agent's tender-portal tab after the bid.

- ERP: "its requirement differs from the early searches: searching it now" at 252–268 s in both a4b9d2c runs; why
  does the early search miss that requirement, and how long does the late search take?

- Qwen reasoning tokens: the requirements and commercials resolvers spend 5–7k output tokens (69–124 s each, at
  ≈55 tok/s) at effort medium, asked twice; in run_39d8950d739e2e2a 3:04→5:08 was nothing but resolver calls. Try a
  smaller question (only the evidence each part needs), or `low` with a code check that sends it back on a gap;
  check with `tools/resolver_eval.py --repeat` before any test run.
- Queue waits on the hosted Qwen: p50 4 s per call, 13 min summed in run_cd888fae0ebef8da; fewer, larger steps help.
- ERP searches are the critical path after the merge (264→448 s in run_364ee0e5b5151237): see how many steps each
  search takes and whether the extract call waits on anything; never cut a search's own budget for it.
- Submit: 22 sequential steps after the bid arrives (5 min in run_a65e32634be4efce); fewer, fuller `form` calls per
  position, wording kept abstract.
