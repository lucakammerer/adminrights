# Quality and release

How a change gets from a branch to a submission. Only Luca starts test runs and submits.

## Branches and the test loop

Finn pushes to `p1/<topic>`, Yazan to `p2/<topic>`, each started from main. `tools/ci.py` runs every 5 minutes
(`python tools/ci.py`, one tick; a session loop repeats it):

1. Fetch. Candidates, in order: the base (origin/main plus Luca's local commits), each `p1/*` and `p2/*` head
   merged onto the base, and all of them together once there are two or more. A merge conflict is reported to the
   owner, never resolved by the loop.
2. Skip what was tested: the key is the git tree of `agent/`, the only part that gets uploaded.
3. Free gates: compile, `tools/audit_package.py` (no public-1 value, no own browser), and the unit tests in `tests/`
   (among them the calc golden test, which must score 100).
4. `atira test-run`, at most 2 at once (more distort the time), never while a submission runs.
5. When a run ends: its log goes to `bench/.ci/logs/`, the logged answer is scored with `eval/compare.py`, and a row is
   added to `bench/RUNS.md`. The outcome column is filled by hand: which phase lost the points and whose code it is.

Nothing is pushed. A branch that beats the base goes to main by PR after Luca's yes.

## Tools

| Tool | Use |
| --- | --- |
| `tools/check_release.sh` | Definition of Done check (RULES §9): audit, unit tests, `agent.json`; green = exit 0 |
| `eval/compare.py answer.json` | Points per field against the public-1 reference `eval/expected.json` |
| `tools/score.sh` | Local dry run against the scouting sites (`DRY_RUN=1` stops before the submission), scored with `eval/compare.py`; no sandbox run needed |
| `tools/audit_package.py [--agent DIR \| --package ID] [run.log ...]` | Fails on a public-1 value (reference values plus ids, hosts, site path segments and addresses from run logs), an own browser launch or an API key; `--package` audits what was uploaded |
| `tests/` | Unit tests; `tests/fixtures/facts.json` holds the complete facts of one public-1 run |
| `bench/RUNS.md` | One row per run: platform quality, offline score, time, cost, cause |

`eval/`, `tests/` and `bench/` hold public-1 values on purpose and are never uploaded.

## Reading a run

The platform scores only a signed answer. A run that ends unsigned scores 0 even with a correct answer, so the
offline score of the logged `[answer]` line is the second number to look at: it separates "wrong facts" from "ran out
of time". Who gets the cause: [plan §14.3](IMPLEMENTATION_PLAN.md#143-triage-of-test-run-results), files by
[CODEOWNERS](../.github/CODEOWNERS).

## Submission gate

All must hold before a submit is proposed:

- A test run of exactly this commit signed a complete bid and was eligible.
- Its quality beats the best submission, or it is more robust and the end is near: the final uses the latest passed
  submission, not the best.
- `tools/audit_package.py` passes on the repo and, after upload, with `--package` on the submission; no fixed click
  paths and no dev scripts in `agent/`.
- The docs match the code.
