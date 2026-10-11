# Night loop: generalization (`gen`, branch `luca/night-gen`)

## Morning summary

- **Merge candidate 4 (a140f33):** the commercials resolver asks once more when Qwen's answer stops after the
  discount (no positions), bounded by the stage deadline. In run_cf4790f7da25d77b that one answer cost about 40
  points (FX, metal, cartons, commitments all empty). Sandbox check: see iteration 4.
- **Merge candidate 3 (eec30f0):** `form` reports a dependent choice that is still closed as "disabled: apply the
  earlier choice first" instead of "no option ...; options: ['choose']", after one wait. The old message plausibly
  caused the 9-minute configurator loss in run_dba11642f54df6c6. Sandbox run_cf4790f7da25d77b submitted cleanly
  (56.9, lost in the commercials resolver, see iteration 3).
- **Merge candidate 2:** `calc.number` reads space/apostrophe grouping (`1 234,50`, `1'234.50`) and comma-locale hints
  other than German (iteration 2). Before, such a price ≥ 1000 parsed as 1 and `1234,50` with a `fr-FR` hint as
  123450. No change on public-1.
- **Reader commit, sandbox:** two runs of ea63e98: 80.1 (sandbox tool timeouts after the login) and 15 (submit stuck in
  the configurator after a correct answer at 417 s). Neither failure is in the reader; the clean local control is
  74/74. Treat the reader as neutral on public-1, positive on other software.
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

### 2 · 2026-10-11 02:58 · calc: numbers in other locales

Collected first: the reader commit's two sandbox runs (ea63e98, same package):
- `run_a1e07a5b9bdce64b` 80.1: three 60 s browser-tool timeouts on tender-portal reads right after the login, so
  phase 1 hit its cut and three base prices were missing. The same login page read fine in the second run, so this
  points at the sandbox rather than the reader.
- `run_dba11642f54df6c6` 15: the answer at 417 s equals the 100 runs (all five positions), but submit lost 9 min on
  the configurator's dependent dropdowns: it set all four in one `form` call with one apply click, the dependent
  dropdown stayed disabled, and select/keys/reloads never recovered it. It signed with every position omitted. In the
  80.1 run the model clicked apply after each dropdown and it worked. Nothing in the reader diff touches selects or
  disabled state; this is a submit-agent weakness on stateful forms (Finn: submit), and a likely trap on unseen
  portals too.

Hypothesis: `calc.number` reads only `.`/`,` notation. Prices of 1,000 or more that other locales group by spaces or
apostrophes (`1 234,50`, `1'234.50`) parse as 1; a `fr-FR`/`es-ES` hint turns `1234,50` into 123450; a `de-CH` hint
does the same to `1234.50`. Public-1 never shows these, so nothing caught it.

Fix (`calc.number`, `calc.hinted_decimal`): a number shows its own format whenever it can (both separators, one
repeated, space or apostrophe grouping, a lone separator before anything but exactly three digits); only `12,345` /
`12.345` follow the hint, which may be a whole locale tag (with the comma-decimal languages, `-CH/-LI/-MX/-US` as
point), a sample like `1 234,56`, or words like "decimal comma". Tests in `tests/test_calc.py`.

Evidence: 36 hand cases, old against new: no case the old parser got right is wrong now. Wrong before and right
now: every grouped price, comma-locale hints, `German format` hints, `decimal comma`. Adversarial review round 1
FAILED (space grouping merged `12,50 100` into 12.501; a hint starting "no ..." read as Norwegian), fixed; round 2:
FAILED on hints with words after the tag (`de-DE format`) and `0,125` under a `de-CH` hint, both fixed and checked case by case (`ab 100 250,00` stays joined: wrong before too, a quantity in `price_as_shown` cannot be told apart from French grouping). Unit tests and `check_release.sh` green, audit clean.
Unmutated local control of the final reader (`gen-new-ctrl3`): gather 74/74, 152 model calls (old reader 163), longest agent 193 s: the reader commit is not worse on public-1. Not a check of the calc change: public-1 shows no grouped or comma-locale numbers, so its answer is unchanged by construction (unit tests cover the replayed public-1 facts).

Verdict: keep. Pure parser fix, no behaviour change on public-1; it removes a silent 1000x error on any unseen ERP
that prints prices the French, Swiss or Scandinavian way. No sandbox run started: public-1 cannot show the
difference, and my last two runs on this branch answer the reader question already.

Next: the configurator failure in `run_dba11642f54df6c6` is the bigger risk on unseen portals (dependent dropdowns
that only enable after an apply click or a trusted event). Submit is Finn's; worth a stress page with dependent
selects to measure how often the submit agent gets stuck.

### 3 · 2026-10-11 03:10 · browser: a closed dependent choice reads as "disabled", not as "no option"

Hypothesis: in `run_dba11642f54df6c6` submit lost 9 min in the configurator after setting all dependent choices
before one apply click. A local probe (`tests/test_browser.py`, `/config`: a choice that opens only once the earlier
one is applied) shows what `form` told the model: `no option '600'; options: ['choose']`. With the submit mission's
"the page may word a value differently" that invites rewording values instead of pressing apply. Any configurator on
unseen software that opens choices server-side or a moment later by script hits the same message.

Fix (`Tab.form`): a field still disabled (`:disabled`, `aria-disabled`) gets one `settle`; if it stays disabled the
step stops with "disabled: if it depends on an earlier choice, apply that choice first". A select without the wanted
option is re-read once after a `settle` (options a script loads a moment after the change). The normal path (enabled,
option present) waits for nothing new.

Evidence: new test fails on the old `form` ("no option") and passes now, with the scripted case (options added
600 ms after the change) passing too and the closed case failing within 4 s; 96 tests and `check_release.sh` green,
audit clean, adversarial review PASS (nits only). Commit eec30f0. Sandbox `run_cf4790f7da25d77b`: 56.9, 12.5 min, $0.272.
The submit path this change touches was clean: five positions in five `form` calls with an apply after each choice
(70 s), verify_summary all match, signed. The lost points come from the commercials resolver: webmail kept every
record, but its single Qwen call (55k chars) took 219 s and came back with FX, metal index, cartons and commitments
empty. That is not in this diff.

Verdict: keep. It changes only what the model is told when a choice is closed, and waits only when a field is
disabled or lacks the option. One sandbox run shows no regression on the configurator.

Next: commercials on Qwen is now the largest single loss seen on this branch (a whole stage empty from one answer).
Worth checking with `tools/resolver_eval.py --repeat N` on recorded evidence whether Qwen often leaves commercials
fields empty, and whether its result could be validated (records kept but values empty means ask again while time
allows). That touches resolvers (Luca's) and llm (Finn's), so measure first.

### 4 · 2026-10-11 03:30 · resolvers: a commercials answer without positions is asked once more

Hypothesis: in `run_cf4790f7da25d77b` (56.9) the commercials call (18.7k tokens in, 4.1k out, 105 s) returned valid
JSON with only `tender_reference` and `discount`. `parse_object` accepted it, every per-position and rate fact
(FX, metal index, cartons, commitments) became empty, and the sweep never noticed: `sweep.gaps` checks FX and metal
only against ERP results (none yet) and cartons only for listed positions (none listed). On any dataset, one lazy
Qwen answer empties a whole stage.

Fix (`resolvers.commercials`): when the tender lists positions and the answer has none, ask once more if at least
`RETRY_MIN` (60 s) is left before the stage cut, bounded by `wait_for` to end `RETRY_MARGIN` (10 s) before it; keep
the second answer only if it has positions; a failed second call keeps the first. Normal path unchanged (one call).

Evidence: unit test (`tests/test_sites.py` `CommercialsTest`): complete answer = 1 call; partial then full = full;
partial twice = partial; partial then timeout = partial. Check release green, audit clean. Adversarial review round
1 FAIL (a late retry that timed out or hit the stage cut dropped the first answer, so `safe` returned `{}`), fixed;
round 2 PASS. Local measurement of how often Qwen answers without positions (`resolver_eval --repeat 8`) impossible:
every local call got HTTP 429 from 03:35 on (same as iteration 1). Commit a140f33. Sandbox `run_2bc252ed46c457d7`
started 03:50 (normal-path regression check; the retry itself fires rarely).

Verdict: pending the sandbox run.

Next: measure the partial-answer rate with `tools/resolver_eval.py --repeat 8` once the local 429s stop; if it is
more than rare, a hedged pair (`first` that accepts only answers with positions) would save the retry's 100 s.

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
