# Night loop: score and efficiency (`luca/night-score`)

## Morning summary

Best Qwen candidate so far: **f5e86da** (main 1fa269f + `luca/radical-speed` merged, Qwen default, paging fix).
Test runs: 100 / 11:01 / $0.201 / **132.8 $·s** (run_364ee0e5b5151237), 100 / 13:12 / $0.249 / 197 $·s
(run_a65e32634be4efce). Main on Qwen the same night: 100 / 15–16 min / 258–262 $·s. Our submission 70 $·s (Haiku),
rank 1 25 $·s. Distrust: the baselines ran under heavy Qwen queueing (13 min of queue wait), the merge runs under
almost none; a paired run (both at once) is pending. Not a submit candidate on $·s: still ~2–3× our Haiku
submission. Note also run_0b1441de63cf8acb (not ours, all Haiku): 100 in 5:09, 28.1 $·s.

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

## Backlog

- Qwen reasoning tokens: the requirements and commercials resolvers spend 5–7k output tokens (69–124 s each, at
  ≈55 tok/s) at effort medium, asked twice; in run_39d8950d739e2e2a 3:04→5:08 was nothing but resolver calls. Try a
  smaller question (only the evidence each part needs), or `low` with a code check that sends it back on a gap;
  check with `tools/resolver_eval.py --repeat` before any test run.
- Queue waits on the hosted Qwen: p50 4 s per call, 13 min summed in run_cd888fae0ebef8da; fewer, larger steps help.
