# Night loop: generalization (`gen`, branch `luca/night-gen`)

## Morning summary

- **Merge candidate 6 (a36d345 + 9a59bdf), most important:** `settle` closed in-page dialogs with an unbounded
  `frame.evaluate` in every frame. A frame whose server never answers blocked it forever, so every `read` on such a
  page ran into the 60 s tool timeout. That cost `run_a9338f4c12a5d253` (15: submit hung twice for 77 s, signed with no
  positions) and plausibly `run_a1e07a5b9bdce64b` (80.1, three 60 s read timeouts). Now each frame waits under one 3 s
  cap and a stalled frame is not waited for again until it navigates. Also `form` finds a field by any name the reader
  shows (label, placeholder, title, name) and in frames, and fails at once instead of after 30 s. After the fix:
  `run_7705434641fff595` scored 100 in 6:23 (85.8 $·s), the best Qwen run so far (one sample).
- **Merge candidate 5 (0c59c29):** downloads in office formats and other encodings. XLSX/ODS row by row with labels
  next to values, dates as dates, hidden sheets/rows/columns dropped; DOCX/ODT/PPTX as paragraphs, hidden runs and
  tracked deletions dropped; UTF-16 and Windows-1252 text decoded. Before: raw XML or NUL-interleaved garbage. Public-1
  path unchanged; sandbox run_99fdafd5b89f1999 100 in 9:43 (121.6 $·s, best Qwen so far).
- **Merge candidate 4 (a140f33):** the commercials resolver asks once more when Qwen's answer stops after the
  discount (no positions), bounded by the stage deadline. In run_cf4790f7da25d77b that one answer cost about 40
  points (FX, metal, cartons, commitments all empty). Sandbox run_2bc252ed46c457d7: 100 in 9:28 on the normal path (retry not
  fired).
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
(normal-path check): 100, 9:28, $0.221 (125 $·s, best Qwen time so far; one sample, the speed is not from this
change). Commercials answered completely in one call (56k chars, 170 s), so the retry did not fire.

Verdict: keep. Normal path unchanged and clean in the sandbox; the retry turns a silent stage loss into one bounded
extra call, and a failed or late retry keeps the first answer.

Next: measure the partial-answer rate with `tools/resolver_eval.py --repeat 8` once the local 429s stop; if it is
more than rare, a hedged pair (`first` that accepts only answers with positions) would save the retry's 100 s.

### 5 · 2026-10-11 03:45 · browser: office files and non-UTF-8 text in downloads

Hypothesis: trap 8 says values may sit in downloaded files, and the private dataset "splits information differently".
`describe_file` read only PDF, ZIP and UTF-8 text. Probes (old code): a UTF-16 export (Excel "Unicode text") came out
as NUL-interleaved garbage, a Windows-1252 CSV lost `€` and umlauts, an XLSX came out as raw XML with every label in
`sharedStrings.xml` cut off from its cell, dates as day serials, hidden sheets and rows included (decoys), and a DOCX
as raw XML whose markup fills the 14k-char budget before the text ends. Any unseen portal that ships a price list
as XLSX or a specification as DOCX would hand the model unusable text.

Fix (`browser.describe_file`, new `decode`, `office_text`, `xlsx_text`, stdlib only): text by BOM, UTF-16 without
BOM, UTF-8, else Windows-1252 (only when invalid sequences outnumber valid ones); XLSX/ODS row by row, cells
tab-separated at their column, date-formatted cells as ISO dates (1900 and 1904 systems), hidden sheets, rows and
columns dropped; DOCX/ODT/PPTX paragraph by paragraph, table cells tab-separated, hidden runs, deleted tracked changes,
ODF hidden text, collapsed rows and hidden slides dropped. Anything that fails or is no office file falls back to the
old member listing. Public-1 ships a ZIP of UTF-8 CSV/TXT: the office path is never taken and valid UTF-8 decodes
identically, so its reading is unchanged by construction.

Evidence: new test `test_office_files_and_other_encodings_are_read` fails on the old code, passes now; files written
by openpyxl and python-docx read correctly (labels next to values, date as `2026-03-01`, hidden run dropped);
malformed 2 MB part 0.44 s. 98 tests and `check_release.sh` green, audit clean. Adversarial review round 1 PASS with
gaps (cp1252 fallback on one stray byte: a regression; tracked-change deletions, hidden columns/slides, ODF hidden
text leaking; uncaught `TypeError`; empty text for Strict OOXML; 1904 dates; time formats as dates), all fixed.
Round 2 PASS; two of its low edges fixed too (a literal `\ufffd` in valid UTF-8, moved-away text shown twice).
Left by choice: style-based hiding (needs style resolution), multi-paragraph table cells split a row, hidden runs
over 5000 chars (bound against slow matching on malformed XML), ODF conditional hidden text always dropped.

Commit 0c59c29. Sandbox control `run_99fdafd5b89f1999` (public-1 cannot exercise the new path; it checks the branch
head for regressions): 100, 9:43, $0.208 (121.6 $·s, best Qwen value so far), every field full points.

Verdict: keep. Unchanged reading on public-1 by construction and in the sandbox; on unseen software a price list in
XLSX, a specification in DOCX or an export in UTF-16/Windows-1252 now reaches the model as readable text with
decoys dropped instead of raw XML or garbage.

Next: a stress variant that serves the tender documents as XLSX/DOCX (or UTF-16 CSV) instead of the public-1 files
would measure this end to end; `run_agents.py` mutates only HTML today.

### 6 · 2026-10-11 04:15 · browser: `form` finds a field by the name the reader shows, in frames too

Hypothesis: the reader names a field by aria-labelledby, aria-label, `label[for]`, a wrapping label, else its
placeholder, title or name; `form` resolves `field` only with Playwright's `get_by_label` and only in the main frame.
On software whose inputs carry only a placeholder or title, or whose form sits in an iframe (trap 8), every
`{"field": ...}` step the submit mission asks for waits Playwright's 30 s default and fails with a timeout text;
`click` by name misses buttons in frames the same way.

Fix (`Tab.named`, `Tab.form`/`Tab.step`, `Tab.settle`): a field is looked up by exact label or placeholder, then
partial label or placeholder, then title or name attribute (hidden inputs skipped), in every frame; a button by exact,
then partial role name, in every frame. Nothing found: one `settle`, one more search, then "no field ... use the label
the page shows, or its ref" at once. `settle` also waits for child frames (in parallel, at most `FRAME_WAIT` 3 s); a
field step whose frame was replaced mid-step is tried once more (fields only, never a click or ref step, so nothing is
applied twice).

Evidence: new test `test_form_finds_fields_by_the_reader_s_name_and_inside_frames` (placeholder-only input, title-only
select with a non-ASCII title next to a hidden input of the same name, role=button div, the configurator in an
iframe, a missing field) fails on the old code after 91 s (three 30 s timeouts, "Locator.evaluate: Timeout 30000ms
exceeded"); passes now, 50 repeats without a flake after the frame-race fixes (before them 1 in 5 and 1 in 25
failed). 99 tests, `check_release.sh` green, audit clean. Adversarial review round 1 FAIL (name match hit hidden inputs
before a partial label; `json.dumps` escaped umlauts so CSS never matched; frame waits serial, 3 s each), all fixed;
round 2 PASS. Commit a36d345.

Sandbox `run_a9338f4c12a5d253` (a36d345): 15, 17.5 min, $0.203. The new lookup worked: every `field` step resolved,
none FAILED. The answer was complete at 663 s, but after one click in the configurator two `read` calls each hung
about 77 s (past `TOOL_TIMEOUT`) while the portal page was still loading. The model then rebuilt the page by ref, ran
out of time and signed with `positions: []`. Root cause, reproduced locally on the old code as well:
`settle` closes in-page dialogs with an unbounded `frame.evaluate` in every frame, and on a frame whose server never
answers that blocks forever, so every read on such a page lasts until the 60 s tool timeout. The same symptom
("three 60 s browser-tool timeouts on reads") appeared in `run_a1e07a5b9bdce64b` (iteration 2) on older code.
Follow-up 9a59bdf: each frame's load wait and dialog close run as tasks under one 3 s cap; a frame still loading at
the cap is not waited for again until it navigates. Test `test_a_frame_that_never_loads_does_not_hold_up_reads`:
old code 20 s (until the test server gave up), new code under 4 s; a form step on such a page takes 3.3 s, a missing
field 0.4 s. Review PASS after a third round (a frame marked stalled must be waited for again after it navigates).
Sandbox `run_7705434641fff595` (9a59bdf): 100, 6:23, $0.224 (85.8 $·s, best Qwen so far), no idle stretch over 60 s,
no model error.

Verdict: keep both commits. The lookup is a strict superset of the old one (exact
label first, as before) and fails fast instead of after 30 s. The stalled-frame bound removes a 60 s-per-read hang
that has now cost two sandbox runs.


## Backlog

- Check how often `read` hits `TOOL_TIMEOUT` across recent team runs (grep stdout for a `read` followed by 60+ s of silence); if the 9a59bdf runs show none, the stalled-frame fix is the cause of those losses.

- Stress: serve the tender documents as XLSX/DOCX/UTF-16 CSV (needs a file mutation in `run_agents.py`).

- Under a 429 burst the gathering agents lose whole stages (`gen-new-ctrl`: every commercial field). If the sandbox's
  run proxy ever limits the same way, a run scores near 0: worth a backoff that waits out a 429 within the stage's
  deadline instead of burning retries (llm.py, Finn's file: propose, don't change).

- A stress mutation whose links have no href at all on result lists (all record links scripted), so URL guessing is
  impossible: would separate the reader arms on points.
- Checked (iteration 5): `common.context` and `common.reference` strip `## Site access` only if present; nothing else
  depends on brief headings.
- `common.reference` takes the brief's first parenthesised identifier; a brief that writes the reference otherwise
  gives the tender agent no hint (the answer's reference still comes from the resolvers).
