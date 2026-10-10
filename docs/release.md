# Quality and release

How a change gets from a branch to a submission. Only Luca starts test runs and submits.

## Branches and the test loop

Finn pushes to `p1/<topic>`, Yazan to `p2/<topic>`, each started from main. `tools/ci.py` runs every 5 minutes
on the server `luca-kammerer` from a clone of the repo (`python tools/ci.py`, one tick):

1. Fetch. Candidates, in order: origin/main alone, each `p1/*` and `p2/*` head and the clone's own pushed branch
   merged onto origin/main, and all of them together once there are two or more. Every branch is compared with main,
   never with another unmerged branch. A merge conflict is reported to the owner, never resolved by the loop.
2. Skip what was tested: the key is the git tree of `agent/`, the only part that gets uploaded.
3. Free gates: compile, `tools/audit_package.py` (no public-1 value, no own browser), and the unit tests in `tests/`
   (among them the calc golden test, which must score 100).
4. `atira test-run` while fewer than 4 of the team's test runs are active (manual ones count), never while a
   submission runs. The rest wait for the next tick in this order.
5. When a run ends: its log goes to `bench/.ci/logs/`, the logged answer is scored with `eval/compare.py`, and a row is
   added to `bench/RUNS.md`. The outcome column is filled by hand: which phase lost the points and whose code it is.

Nothing is pushed. A branch that beats main goes to main by PR after Luca's yes.

### Running the loop

- Needs git with read access to origin, `atira` on the PATH and signed in for the team (`atira login`), `uv` and
  Python ≥ 3.10. No environment variables. The tests sync `agent/.venv` on first use.
- The browser tests need Playwright's Chromium for the pinned Playwright: after a Playwright bump, run
  `uv run --project agent playwright install chromium` in the clone, or every candidate fails the gate.
- State outside git: `bench/.ci/state.json` (tested `agent/` trees and their runs, runs still open) and
  `bench/.ci/logs/` (run logs; the audit also reads them). Without them a fresh clone tests the current main once
  more and doesn't collect runs that another machine started.
- Rows it adds to `bench/RUNS.md` stay in that clone until committed.
- Cron, never two ticks at once: `*/5 * * * * cd <clone> && flock -n bench/.ci/lock python3 tools/ci.py >> bench/.ci/ci.log 2>&1`

## Tools

| Tool | Use |
| --- | --- |
| `tools/check_release.sh` | Definition of Done check (RULES §9): audit, unit tests, `agent.json`; green = exit 0. GitHub Actions (`.github/workflows/release-check.yml`) runs it on every PR and push to main |
| `eval/compare.py answer.json` | Points per field against the public-1 reference `eval/expected.json` |
| `tools/rescore.py [run.log ...]` | The logged facts of past runs (default `bench/.ci/logs/`) through today's `calc.compute`, scored per run: a calc change checked without a test run (`facts` itself is not replayed) |
| `tools/score.sh` | Local dry run against the scouting sites (`DRY_RUN=1` stops before the submission), scored with `eval/compare.py`; no sandbox run needed |
| `tools/resolver_eval.py [FIXTURE] [--repeat N]` | `requirements` and `commercials` on recorded evidence (`eval/fixtures/resolvers`), as recorded and with the changes in `eval/mutations.py` (newer, future-dated, look-alike and unauthorized approvals, a shifted index window, other number formats, newer, future, set and withdrawn quantities); each pass scored against the facts the change leaves; model calls only, no browser |
| `tools/audit_package.py [--agent DIR \| --package ID] [run.log ...]` | Fails on a public-1 value (reference values plus ids, hosts, site path segments and addresses from run logs), a German word of the public sites the brief doesn't tell every team (quoted labels in `scouting-notes.md`, the scouted Q&A), an own browser launch or an API key; `--package` audits what was uploaded |
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
