# Night loop: generalization (`gen`, branch `luca/night-gen`)

## Morning summary

- **Candidate to merge:** the reader commit of iteration 1 (styled tables and script-driven controls). It closes two
  gaps that matter only on other software: values in styled span/div rows merged into one number (`100` and `12,50`
  read as `10012,50`), and ARIA widgets, links without href and click-handler elements had no ref, so the model could
  not click them. Public-1 is unaffected (gather 74/74 unmutated and under S2). Sandbox evidence: see iteration 1.
- **Fixed tool:** `run_agents.py --mutate` was broken (every mutated page raised `opts is not defined` and the request
  hung), so earlier S2 numbers on this branch's base never measured anything mutated.
- **Distrust:** one stress run per arm; the step and model-call savings under `--widgets` are a single sample.

## Iterations

### 1 · 2026-10-11 01:42 · reader: styled tables and script-driven controls

Hypothesis: other software renders tables as styled spans/divs and navigation as script-handled elements; the reader
separated values only by tag and gave refs only to native controls, so on such a site prices would merge and records
would be unreachable.

Evidence:
- Probe page (outside the package): old reader `Bore50Stroke200`, `10012,50`; `role=link`, `role=checkbox`,
  `role=switch`, `<a>` without href, `onclick` divs and contenteditable got no ref. New reader keeps values apart
  and gives each a ref.
- New opt-in stress mutation `--widgets` (`tools/stress/mutations.js`): tables as flex rows of spans, every other link
  a pointer span a page script follows. On the recorded mailbox page the old reader leaves the real record's row and
  the next-page control without a ref; `tests/test_mutations.py` now checks facts and usable links under it (fails on
  the old reader, passes on the new).
- Live gather (`tools/stress/run_agents.py --resolve`, Qwen), fixtures in `tools/stress/runs/gen-*`:

  | Arm | Reader | Gather | Model calls | Tender-portal turns | Longest ERP search |
  | --- | --- | --- | --- | --- | --- |
  | `gen-base-ctrl`, unmutated | old | 74/74 | 163 | 26 | 190 s |
  | `gen-old-w3`, `--mutate 3 --widgets` | old | 74/74 | 168 | 35 | 216 s |
  | `gen-new-w3`, `--mutate 3 --widgets` | new (first version) | 74/74 | 151 | 23 | 149 s |
  | `gen-new-ctrl`, `gen-new-11` (parallel), `gen-new-ctrl2` | new (final) | invalid | | | |

  The final-reader arms are invalid: from about 5 min into the parallel pair, the hosted Qwen answered every call of
  this client with HTTP 429 ("too many inference-token requests from this client"; 40/74 and 38/74 with every
  failure a skipped call), and `gen-new-ctrl2` alone got 429 on all 13 calls (4/44). Not the reader: the model never
  answered.

  The old reader survives `--widgets` live because half the links keep their href and the agent guesses URLs; the
  mutation does not separate the arms on gather points, only (one sample) on steps.
- Adversarial review: first FAIL (role=combobox divs rendered fillable, links without href swallowed inner controls,
  empty anchors), fixed; second PASS.

Commits: b031f2b (stress tool), 68e6e6c (reader). Verdict: pending a valid final-reader control and a sandbox run
(team at 3 active test runs at 02:05, so none started).

## Backlog

- Under a 429 burst the gathering agents lose whole stages (`gen-new-ctrl`: every commercial field). If the sandbox's
  run proxy ever limits the same way, a run scores near 0: worth a backoff that waits out a 429 within the stage's
  deadline instead of burning retries (llm.py, Finn's file: propose, don't change).

- A stress mutation whose links have no href at all on result lists (all record links scripted), so URL guessing is
  impossible: would separate the reader arms on points.
- Hidden assumptions to check: `extract` cuts the brief at `## Rules`, `context` drops `## Site access`: harmless if
  absent, but verify nothing else depends on brief headings.
- `common.reference` takes the brief's first parenthesised identifier; a brief that writes the reference otherwise
  gives the tender agent no hint (the answer's reference still comes from the resolvers).
