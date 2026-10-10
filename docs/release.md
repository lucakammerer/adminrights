# Quality and release

How a change gets from a branch to a submission. Only Person 3 submits, and only after Luca's yes.

## Branches and the test loop

Person 1 pushes to `p1/<topic>`, Person 2 to `p2/<topic>`, each started from main. `bench/ci.py` runs every 5 minutes
(`python bench/ci.py`, one tick; a session loop repeats it):

1. Fetch. Candidates, in order: the base (origin/main plus Person 3's local commits), each `p1/*` and `p2/*` head
   merged onto the base, and all of them together once there are two or more. A merge conflict is reported to the
   owner, never resolved by the loop.
2. Skip what was tested: the key is the git tree of `agent/`, the only part that gets uploaded.
3. Free gates: compile, `eval/leak.py`, no own browser launch outside `browsers.py`, and a calc replay of
   `bench/fixtures/facts.json` that must score 100 with `eval/compare.py`.
4. `atira test-run`, at most 2 at once (more distort the time), never while a submission runs.
5. When a run ends: its log goes to `bench/.ci/logs/`, the logged answer is scored with `eval/compare.py`, and a row is
   added to `bench/RUNS.md`. The outcome column is filled by hand: which phase lost the points and whose code it is.

Nothing is pushed. A branch that beats the base goes to main by PR after Luca's yes.

## Tools

| Tool | Use |
| --- | --- |
| `eval/compare.py answer.json` | Points per field against the public-1 reference `eval/expected.json` |
| `eval/leak.py [--agent DIR] [run.log ...]` | Fails if `agent/` holds a public-1 value: reference values plus ids, hosts and addresses from run logs |
| `bench/fixtures/facts.json` | Complete facts of one public-1 run; `calc.compute` on it must score 100 |
| `bench/RUNS.md` | One row per run: platform quality, offline score, time, cost, cause |

`eval/` and `bench/` hold public-1 values on purpose and are never uploaded.

## Reading a run

The platform scores only a signed answer. A run that ends unsigned scores 0 even with a correct answer, so the
offline score of the logged `[answer]` line is the second number to look at: it separates "wrong facts" from "ran out
of time". Owners: Person 1 for `agent.py`, `llm.py`, `browser.py`, `reader.js`, `agents/submit`; Person 2 for the
website agents and `agents/common.py`; Person 3 for `calc.py` and `agents/resolvers`.

## Submission gate

All must hold before a submit is proposed:

- A test run of exactly this commit signed a complete bid and was eligible.
- Its quality beats the best submission, or it is more robust and the end is near: the final uses the latest passed
  submission, not the best.
- `eval/leak.py` passes; no fixed click paths, no own browsers, no dev scripts in `agent/`.
- The docs match the code.
