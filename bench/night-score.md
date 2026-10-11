# Night loop: score and efficiency (`luca/night-score`)

## Morning summary

Best candidate so far: **a4b9d2c** (f5e86da + two fixes): 100 / 11:20 / $0.230 / 156.2 $·s (run_bd99f53d4d7d5c7f),
100 / 12:52 / $0.235 / 181.6 $·s (run_ba99f2d4eb2f586e). Main on Qwen tonight: 122.6–262 $·s.
- a4b9d2c fixes a quality loss that main has too: `calc.facts` added the ERP's per-material setup fee to the
  commercials' per-position one (run_cf57141fcf4352a0: 84.8). Now the commercials' value, the ERP's only when the
  commercials lack the position. Judgement call: the brief doesn't say where the ordinary setup fee lives; public-1
  has it in the Q&A, and the ERP shows a per-material fee as a decoy. Worth merging to main on its own.
- 7cb21db: the submit agent's `form` call is held once when it types a position's unit price without one of its
  non-zero breakdown values (a bonus typed as 0 cost ~110 s of walking back in run_a65e32634be4efce, and a wrong
  value in run_c086c4a6429b3bd9).
- The radical-speed merge (f5e86da) is **not** shown faster on Qwen: merge 132.8 / 197 / 232.9 $·s vs main
  257.8 / 262 / 122.6 $·s; the one paired pair went to main (122.6 vs 232.9). Load noise dominates.
Our submission 70 $·s (Haiku), rank 1 25 $·s. No Qwen run is a submit candidate on $·s yet.

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



## Backlog

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
