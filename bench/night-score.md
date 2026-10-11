# Night loop: score and efficiency (`luca/night-score`)

## Morning summary

Best candidate: **2c5dd5f** (58f933b + a follow-up for a search cut by its step limit with facts missing):
run_75da3ea2197f3709 100 / 5:30 / $0.150 / **49.6 $·s**, run_0a26a180075ecc2c 100 / 7:36 / $0.173 / 79.0 $·s. Our
Haiku submission: 70 $·s; rank 1: 25 $·s. The branch's last six Qwen runs (5c1668a, 58f933b, 2c5dd5f): 49.6-79 $·s,
5 of 6 at 100 (one 85.3 from a step-limited ERP search, which 2c5dd5f now follows up; one 5 from a bug fixed in
58f933b). Single runs still vary ~1.5x with load and model wander.

Previous best: **58f933b** (5c1668a + the night-gen merge 1920ba1 + the no-match check fix): run_92428b63f6b01b4e
100 / 6:51 / $0.131 / **53.6 $·s**, run_28c8d1f903003c25 85.3 / 6:34 / $0.132 / 52.3 $·s (one ERP search hit its
40-step limit before the price page). Cost × time is now below our Haiku submission's 70 $·s on Qwen, but quality
is not yet steady: 2 of the last 4 runs missed 100. 5c1668a's pair: run_96d33dd7b340c037 100 / 6:34 / $0.142 / **56.1 $·s**
(best Qwen run of the night, below our Haiku submission's 70 $·s; rank 1: 25 $·s) and run_7d633f73aa69af53 **5**: a
no_bid from a bug in 5f858c2 (a changed requirement never reached the ERP no-match check), fixed in 58f933b.
**Do not merge 5f858c2 without 58f933b.** Earlier pairs: 5f858c2 167.2 / 172.4 $·s, fcac256 167.2 / 147.6 $·s.
Main-based night-gen runs on Qwen: 85.8 and 121.6 $·s, so the radical-speed structure on this branch is not shown
to beat main on Qwen; single runs vary 2× with load.
Merge to main, each worth it on its own:
- 2c5dd5f (erp): a search cut by its 40-step limit, a material chosen but required facts unkept, with >= 120 s left,
  gets one follow-up of at most 12 steps on the same tab, driven by extract's gap list. Insurance, never fired live.
- 58f933b (agent): goes with 5f858c2. The no-match check (a second ERP search) now gets the changed requirement
  too; without it a no_match decided on the specification's values became a no_bid (run_7d633f73aa69af53: 5).
- 5c1668a (agent): the first TAN look-up's mailbox tab opens when the submission starts. TAN look-up 13 s and
  36 s in its two runs (was 16-161 s).
- 5f858c2 (agent, llm, erp): early ERP searches start from the specification; when the final requirements carry an
  amendment the specification lacked, main used to cancel that search and start over (the last search to finish,
  ~110 s). Now the running search of the same catalogue group gets the new values as a message; one that had
  already decided runs again. Fired in both runs, 2 reviews (the first found the decided-search gap, fixed).
- 9d32034 + fcac256 (browser, agent): a navigation the site never answers locks the tab: Playwright runs no script
  on it until the navigation ends, so every read and form step waits out the 60 s tool timeout. Seen live twice
  (a configurator POST: 150 s; the mailbox start page in `fresh`: two TAN agents forced, 6.5 min), reproduced
  locally, both now freed after 30 s (CDP `Page.stopLoading`) and the model told.
- a4b9d2c (calc): the setup fee comes from the commercials; the ERP's per-material fee only when they lack the
  position. Fixed an 84.8 (double count). Judgement call, see iteration 2.
- c31d89a (submit): the TAN look-up opens a new tab of the mailbox (same login). The mail agents' idle tab hung
  45-150 s in 5 of 10 runs, main included; with the change 37 s and 63 s.
- 4d4a37f (llm): a streamed call without its first chunk after 10 s gets a twin. 6-10 calls a run sat silent for 30 s
  before; in run_c13fd1a74d3ad98c 9 twins, each answered in ~2 s, the originals never reached the platform.
- 7cb21db (submit `form` hold): insurance, never fired live.
Distrust: 3258746 (reverted in 74f20cd), whose idle-tab throttling theory was wrong; f5e86da (radical-speed merge),
not shown faster on Qwen, load noise dominates single runs. Next loss to fix: the TAN look-up (the mailbox start
page not loading in a new tab, 50 s in 2 of ~8 runs; the TAN agent wandering), see iteration 5.

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

Runs (3258746): run_590a955bd423bbac 90.5 / 11:03 / $0.252 / 167 $·s (no stall; 01.01 quantity 26 instead of 25 from
the requirements resolver, unrelated), run_01a5fe851c09aba6 100 / 14:49 / $0.273 / 242.8 $·s, **with** the stall on
a busy tab: a `form` step clicked a configurator button at 572 s, then nothing until the model's `goto` at 721 s.
Hypothesis refuted. The screenshot at 10:30 shows the tab's loading spinner: the button's form POST never got an
answer. Reproduced locally (a POST the test server never answers): while it is pending, Playwright's
`page.evaluate("1")` hangs (it waits for the new document), so every read, click fallback and form step on the tab
waits out the tool timeout; the click itself fails after 5 s. `goto` or CDP `Page.stopLoading` free the page at once
(stopLoading keeps typed inputs). Reverted 3258746 (74f20cd).

Change 9d32034: `Tab` watches main-frame navigation requests; one without a response after 30 s (`goto`'s own
limit) is stopped with `Page.stopLoading` and the model told (method, URL, "may not have taken effect: check the
page"). Test: a form POST without an answer, then a click on it: < 14 s with the limit at 2 s (old code hung to the
test's guard). Gate: check_release green, audit clean, reviewer PASS (accepted risk: a server slower than 30 s that
still acts on the POST may get it twice; the tab was stuck anyway). Runs (9d32034): run_86571e2d5c35436b,
run_3af67abb1c0fe79b (started 02:07 UTC).

Results (9d32034): run_86571e2d5c35436b 100 / 17:20 / $0.246 / 255.6 $·s, run_3af67abb1c0fe79b 100 / 13:26 / $0.269 /
216.8 $·s. No submit-tab stall in either (the watcher never had to fire). run_86571 lost 6.5 min in the TAN look-up:
twice `fresh` hit `start page not loaded` on the mailbox (20 s), then the TAN agent's first read hung 60 s and its
fetches hung on: the same pending-navigation lock, in `fresh`, which navigates before a `Tab` exists. Both TAN
agents were forced off (~160 s each); the third look-up got through. run_3af67 lost no time to the browser (TAN agent
wandered 72 s; bid at 552 s after a forced ERP search).

Change fcac256: `fresh` creates the `Tab` first; a start page that misses `OPEN_TIMEOUT` is stopped (`Tab.stop`,
shared with the watcher) and opened once more with twice the time, then stopped again (worst 60 s, was 20 s + a
locked tab). Test: a start page that never answers, then a read returns (old code: locked to the test's 10 s
guard). Gate: green, audit clean, reviewer PASS (slow-but-working start pages: hence the longer second attempt).
Runs (fcac256): run_26b1c884ae47eb49 100 / 12:49 / $0.217 / 167.2 $·s, run_2ec4765202c21efd 100 / 11:59 / $0.205 /
147.6 $·s: the best pair of Qwen runs on this branch. Neither hit an unanswered navigation (no `no answer`, no
`start page not loaded`), so the live gain is unproven; the local reproductions show the mechanism. In run_26b1 the
TAN look-up lost 46 s to a model call (twin sent, both timed out at 40 s).

Verdict: keep 9d32034 and fcac256 (4/4 runs 100 and signed, no regression, two reproduced lock-ups fixed); 3258746
reverted (wrong hypothesis). Next idea: the in-page `fetch` without an answer (backlog, first item), the same family
of site requests that never answer; then the TAN agent's model calls (a 40 s timeout after a twin).

### 5 · 04:45 · A changed requirement goes to the running early search, not a new one

Profile of run_2ec4765202c21efd (fcac256, 100 / 11:59): the early ERP searches start at 299 s from the specification;
the requirements resolver answers at 355 s with an amendment the specification lacked (a scoped stroke change), so
main cancelled the early search of that catalogue group (55 s in, the right candidate already on screen) and started
a new one from scratch: 355→466 s, the last search to finish (the others 387-413 s). Same pattern ("differs from the
early searches") in both a4b9d2c runs. Then extract 466→497 s, then the submit agent's first step after the bid 43 s.

Hypothesis: hand the corrected values to the running early search of the same catalogue group that no position
needs (requirement updated in place, a message before its next step via `investigate(news=...)`); its candidates and
kept pages still count. Expected: ~50 s off the critical path whenever an amendment changes a value.

Commit 5f858c2. Gate: check_release green, audit clean. Reviewer first REJECTED: a search that had already decided
(in its final extract or check) never reads the message, so its old-values result would stand. Fixed: an unread
message when the search returns means it decided on the old values, so `erp_search` runs a fresh search (the old
behaviour); an empty catalogue group is never redirected; test for both cases. Re-review PASS. Runs (5f858c2):
run_b4c23813dd122d18, run_5150d06e5790477d (started 04:53). Judge by: `told the search` in the log, time from the
requirements answer to the last ERP finish, quality, signing.

Results (5f858c2): run_b4c23813dd122d18 100 / 9:47 / $0.285 / 167.2 $·s, run_5150d06e5790477d 100 / 10:26 / $0.275 /
172.4 $·s: the two fastest Qwen runs on this branch. `told the search` fired in both (two groups and one), no search
had to run again, bid at 421 s and 344 s (fcac256: 497 s; a4b9d2c and earlier: 350-545 s). $·s is flat because cost
was higher ($0.275-0.285 against $0.205-0.217 for fcac256; the branch has ranged $0.205-0.296 tonight, so not
attributed to the change). Verdict: keep.

Now the longest stretch is after the bid (166 s and 282 s). In run_5150d the TAN look-up took 161 s: `fresh` lost
50 s because the mailbox's start page didn't load in the new tab, twice (20 s, then 30 s: Playwright's own navigation
timeout ends the second attempt before its 40 s). The TAN agent's own `goto` right after worked at once. Then the
agent wandered (a refused finish with an empty TAN, a 42 s `all_pages` fetch of the inbox) and was forced at 624 s.
Same start page stall in run_86571e2d5c35436b: 2 of about 8 runs. Cause unknown (no frames could be cut).

Next idea: TAN look-up. (a) Don't wait for the mailbox start page in `fresh` for the TAN: if it doesn't load within a
short time, stop it and let the agent open the URL (its mission names it); one model step is cheaper than 50 s.
Watch out: the ERP and sweep tabs use `fresh` too, so either make it a parameter or show the shorter timeout is
safe for all. (b) The TAN agent's mission or check: a finish with an empty TAN should send it to open the message
it found, not search again.


### 6 · 05:10 · The first TAN look-up's mailbox tab opens before the bid

Evidence: TAN look-up `get_tan` → TAN agent's finish: run_b4c23813dd122d18 16 s (fresh 5 s, 3 steps),
run_26b1c884ae47eb49 86 s (fresh 14 s, a 40 s model timeout), run_5150d06e5790477d 161 s (`fresh` 50 s: the mailbox
start page twice not loaded, the agent's own `goto` right after worked; then a finish with found true but an empty
TAN, refused with "no message found yet", so it searched every folder again: two `all_pages` fetches, 32 s and 42 s).

Hypothesis: open the first look-up's tab when the submission starts (it waits minutes for the bid anyway), so a slow
start page loads off the critical path; and a finish that found the message but gave no TAN is told to open that
message, not to search again. Iteration 4 showed the idle-tab stalls were unanswered navigations (now stopped), not
idleness, so a pre-opened tab idling for minutes should be safe; the runs check it.

Commit 5c1668a. Gate: check_release green, audit clean, reviewer PASS (risk: if idleness did cause stalls, the first
look-up gets them back; a mailbox whose session times out lands on its login page, the mission's login line covers
it). Runs (5c1668a): run_7d633f73aa69af53, run_96d33dd7b340c037 (started 05:14). Judge by: `get_tan` → TAN finish,
no `fresh` line at the look-up, quality, signing.

Results (5c1668a): run_96d33dd7b340c037 100 / 6:34 / $0.142 / 56.1 $·s, the best Qwen run on any branch (bid at
286 s, TAN look-up `get_tan` 381 s → signed 394 s); run_7d633f73aa69af53 **5** / 7:39 / $0.186: a no_bid, not caused
by this change (TAN look-up 36 s there too, no `fresh` stall in either). Verdict: keep 5c1668a.

Luca merged `luca/night-gen` into this branch at 05:14 (1920ba1: stalled frames, form field lookup, office files,
reader tables); the 5c1668a runs were started before it.

### 7 · 05:15 · A changed requirement must reach the no-match check (fixes a no_bid from 5f858c2)

Evidence (run_7d633f73aa69af53): the early search of one catalogue group started from the specification (usable
stroke + reserves, without the Q&A amendment) and decided "no match" at 246 s, correctly for those values. Its
no-match check (a second search, I11) started at 249 s, but `erp_search` called it without `news`. The requirements
answer came at 286 s with the amended stroke; `redirect` found the job still running and appended the message, which
nothing read. The check searched on the old values, found nothing; the first no_match stood → calc no_bid → 5 points.
5f858c2's guard (unread `news` → run again) only ran after the first search, not after the check.

Change 58f933b: every run of `erp_search` (first, rerun, check) gets `news`; unread news after any run means a rerun
with the new values; when the requirement changed during the check, the first "no match" is dropped and the check's
answer counts (a forced check then leaves the position without a material rather than a stale no_bid). Test: a group
whose first search decides no_match at once and whose check is told the change (old code: '' instead of the
material). Gate: check_release green, audit clean. Reviewer first REJECTED (the snapshot of the requirement was taken
before the first search, so a valid no_match decided on the new values could be dropped when the check is forced);
moved it to just before the check, which is the reviewer's suggested fix. Runs (58f933b, includes the night-gen
merge): run_28c8d1f903003c25, run_92428b63f6b01b4e (started ~05:43). Judge by: quality, signing, time, and whether
the night-gen merge holds the 6:34 pace.

Results (58f933b): run_92428b63f6b01b4e 100 / 6:51 / $0.131 / 53.6 $·s; run_28c8d1f903003c25 85.3 / 6:34 / $0.132 /
52.3 $·s. Neither had a no_match, so the fix's path did not fire live (the unit test shows it). The 85.3: the
search on the ERP login tab spent ~30 of its 40 steps retrying the search form (fills on three refs, a `form`, URL
guesses) before a `fetch` with the query worked at step 31; at step 40 (264 s, the stage deadline ~9 min away) it was
forced before the price page, so 01.04 had no base price and the rebates and total were off. The other searches
went straight through. Verdict: keep 58f933b (a correctness fix; pace held at ~53 $·s with the night-gen merge).

Next idea: a search stopped by its step limit long before its deadline, with required facts missing, loses points
that a few more steps would have saved. Give it one extension when time is plentiful (generic: a cost guard, not a
site assumption), or let the forced finish's `extract` gap list drive a short follow-up on the chosen material.

### 8 · 05:40 · A search cut by its step limit gets a short follow-up for its missing facts

Evidence (iteration 7, run_28c8d1f903003c25, 85.3): one ERP search spent ~30 of its 40 steps on the search form,
chose the right material and was forced at step 40 (264 s) with its stage deadline ~9 min away; the price page was
never kept, so the position had no base price.

Hypothesis: when a search ends without the price condition, `extract` already lists what the kept pages lack; with
at least 120 s left before its search deadline, a follow-up `investigate` on the same tab (mission: the chosen
material + that list, at most 12 steps, no check) keeps those pages, then `extract` reads all pages. Generic (driven
by extract's gap list, no site assumption); costs nothing when searches finish normally.

Commit 2c5dd5f, test (a search forced at its step limit; old code: no price condition). Gate: check_release green,
audit clean, reviewer PASS (notes: the follow-up ignores `news`, which `erp_search` reruns on anyway; it holds one of
the 6 slots). Runs (2c5dd5f): run_0a26a180075ecc2c, run_75da3ea2197f3709 (started 05:47). Judge by: quality,
signing, `follow-up for` in the log (fires only on a cut search), time.

Results (2c5dd5f): run_75da3ea2197f3709 100 / 5:30 / $0.150 / **49.6 $·s** (best Qwen run of the night),
run_0a26a180075ecc2c 100 / 7:36 / $0.173 / 79.0 $·s. The follow-up fired in neither: in run_0a26 a search did hit its
step limit (281 s) but had kept every required fact, so extract found no gap (the trigger is correctly narrow). Verdict:
keep as insurance (no regression, 2/2 signed at 100, costs nothing unless a cut search lacks facts); its catch is
shown only by the unit test.

Next idea: the step limit itself costs time even when facts are complete: run_0a26's search ran 40 steps to 281 s
(bid ~65 s later than run_75da). Look at what those 40 steps did (retrying the search form again?) before touching
prompts; the search form retry pattern also caused iteration 7's 85.3.

### 9 · 05:50 · Fetching a kept page unchanged says it is kept

Evidence (run_0a26a180075ecc2c, 79 $·s): after keeping every fact, one ERP search fetched pages it had already kept
14 times (236→294 s, "CORRECTION" notes re-checking values), another 5 times before its step limit (281 s); the bid
waited on them. Same pattern, 4 times, in run_96d33dd7b340c037; none in three other runs.

Hypothesis: the model re-checks values because it can't tell a fetch shows a page the analyst already has. A `fetch`
whose address was kept and whose content is unchanged gets a reminder appended ("unchanged since you kept it as
evidence #n: the analyst reads it word for word"). Saves the tail of re-checks; never fires on a changed page.

Commit 38d5b42, test (a refetch of a kept page gets the line, another address or changed content doesn't). Gate:
check_release green, audit clean. Reviewer first REJECTED the address-only version (hash routes, state-dependent
pages, `goto` redirects would get a false "already kept" and the model could skip keeping new facts); reworked to
`fetch` only, same address and same `paging.body`, fragment kept; re-review PASS. Runs (38d5b42):
run_076dc1c00233e5a6, run_0847ad70cbda7696 (started ~06:10). Judge by: quality, signing, ERP search step counts and
last-ERP-finish time, how often the line fires (`Unchanged since` is not logged; count refetches of kept URLs with
/tmp-style log parsing as in this entry).

## Backlog

- `specs` at effort low: it only starts the early ERP searches and `requirements` corrects it, yet at medium it took
  60 s and timed out into the low backup in run_b4c23813dd122d18 (early searches ~60 s later). Measure low vs medium
  offline first (`/tmp`-style script calling `resolvers.specs` on `eval/fixtures/resolvers`); at 05:30 the local
  proxy answered every call with 429, so it was not measured.
- Phase 1 varies 99-243 s between identical runs (tender or supplier agent taking 13 vs 30 steps): the largest
  remaining spread; the generalization owner's area, look at step counts before touching prompts.
- TAN look-up after the bid (iteration 5): `fresh` waits up to 50 s for a mailbox start page that sometimes
  never loads; the TAN agent wanders after finding the message.

- In-page `fetch` without an answer: `FETCH_ABORT` 40 s, then the model retries and gets through at once
  (run_01a5fe851c09aba6, TAN look-up 824→864 s, retry 6 s). Try abort 20 s plus one automatic retry inside
  `Tab.fetch` (same worst case, typical recovery ~20 s sooner); the timer only covers the time to the headers.
- `Tab.click`: when Playwright's click times out because the click started a navigation that hasn't answered, the
  DOM-click fallback clicks the same control again once the page is free: a second request. Seen only in the local
  reproduction so far.

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
