# Night loop: score and efficiency (`luca/night-score`)

## Morning summary

Pending: no candidate yet. Reference points: our submission 70 $·s (Haiku), rank 1 25 $·s, best Qwen test run
144 $·s (13 min).

## Iterations

### 1 · 01:50 · Structural speedups of `luca/radical-speed` on Qwen

Hypothesis: on Qwen, wall time is spent in model output (≈45 tok/s, reasoning included) and in serial stages.
`luca/radical-speed` (Luca, not on main) removed serial stages: ERP searches start from the specification, commercials
in three parallel parts, the submission starts early, webmail logs in once and fans out, cache-friendly trimming. It
reached 9–10 min on Haiku. Merge it onto HEAD while Qwen stays the default model and compare with two baseline Qwen
runs of HEAD.

Baseline (HEAD 1fa269f, Qwen): run_c7805bca216fa2e0, run_39d8950d739e2e2a.

## Backlog

- Qwen reasoning tokens: the requirements and commercials resolvers spend 2–3.5k output tokens (60–80 s each) at
  effort medium; asked twice.
- Queue waits on the hosted Qwen: p50 4 s per call, 13 min summed in run_cd888fae0ebef8da; fewer, larger steps help.
