# AGENTS.md

We are building an agent system for the Atira hackathon ([challenge `rfq`](https://ehl-challenge.atira.ai/challenges/rfq.md))
that turns a public tender into one signed bid. Four websites, 20 minutes, no human in the loop. This file is for
you as a coding agent; humans read `README.md`.

## Non-negotiables

- **A model decides.** Where to navigate, what to search for and which documents matter are chosen by a model at run
  time. Code may read, parse, calculate, fill forms and paginate, but never follow a fixed click path or crawl.
  Otherwise the reviewer rejects the package.
- **No website values in the package.** No references, material numbers, prices, discounts, logins or TANs, not even
  as defaults, fallbacks, examples or in prompts. What the brief tells every team is fine.
- **The private dataset counts most.** Different software, navigation and site names, information split differently.
  Nothing may assume what public-1 looks like.
- **Code does the arithmetic.** Every calculation of the bid rules lives in `agent/calc.py` (Decimal, HALF_UP),
  never in a model.
- **Facts come from evidence only.** Values come from pages an agent kept with `save_evidence`, not from a model's memory.
- **Ranking:** eligible (correct tender reference) → quality → cost × time. No answer scores 0.

## Where things live

- `agent/` is the package; only it gets uploaded, the agent READMEs included, so they must hold no public-1 values
  either. Everything outside (`docs/`, `eval/`, `tools/`, `bench/`) stays local.
- `agent/agent.py`: orchestration only (`main`: phases, deadlines, data flow)
- `agent/agents/<name>/`: one folder per agent with `agent.py` (mission, schema, `run`) and `README.md` (its
  documentation); `agent/agents/common.py`: shared system prompt, brief context, schema helpers
- `agent/llm.py`: the one tool loop (`investigate`) and `ask_json`
- `agent/browser.py`, `agent/reader.js`: browser tools; a page as text with `[n:kind "label"]`
- `agent/calc.py`: facts assembly (`facts`) and the bid arithmetic (`compute`)
- `agent/run.py`, `agent/browsers.py`: run contract and browsers (starter kit)
- `docs/`: what spans agents: `RULES.md` (every rule we are judged by), `IMPLEMENTATION_PLAN.md` (the system, the
  target, the backlog), `challenge.md`, `calc.md`; start at `docs/README.md`
- `eval/`: reference answers, the scorer `compare.py` and public-1 data; `tests/`: unit tests; `tools/`: dev
  helpers (`dev-env.sh`), the package audit `audit_package.py`, the test loop `ci.py`; `bench/RUNS.md`: every run

## Who owns what

Three owners, one KPI each ([plan §14](docs/IMPLEMENTATION_PLAN.md#14-work-split-and-timeline)); file owners in
[`.github/CODEOWNERS`](.github/CODEOWNERS) review every change to their files.

- **Efficiency, Finn:** cost × time. `agent.py`, `llm.py`, `agents/submit/`, `agent.json`.
- **Generalization, Yazan:** works on unseen sites. `browser.py`, `reader.js`, `agents/common.py`, the four site
  agents, `tools/stress/`.
- **Quality & Release, Luca:** score 100, every run signs, audit clean; runs test runs and submits.
  `calc.py`, `validate.py`, `agents/resolvers/`, `tests/`, `eval/`, `tools/`, `bench/`, `docs/`.

Every PR reports dry-run score, run time and cost and may not lower the score. Nothing runs while a scored submission
runs.

## Commands

```sh
atira models proxy                                  # terminal 1, keep it open
cd agent && eval "$(atira scout --env)"             # terminal 2: scouting logins, model variables
HEADLESS=1 uv run --no-sync python agent.py         # one local run, never counts
tools/score.sh                                      # from the repo root: local dry run (DRY_RUN=1, no submission) + points per field
uv run --project agent --no-sync python -m unittest discover -s tests   # from the repo root, in seconds
tools/check_release.sh                              # before every submit: audit, tests, agent.json
atira test-run .                                    # sandbox, points per field, not on the leaderboard
python3 tools/runs/serve.py                         # run dashboard: what each run tested, its time, how to improve
atira submit .                                      # only after Luca approves and docs/RULES.md §9 holds
```

## Branches and test runs

Finn pushes to `p1/<topic>`, Yazan to `p2/<topic>`, started from main. `tools/ci.py` tests every new head within
minutes; results land in `bench/RUNS.md`. Details and the submission gate: `docs/release.md`.

## Glossary

- **Run:** one attempt at one scenario; brief, logins and schema come from `GET /v1/runs/current`.
- **Brief:** the task with the 29 bid rules, delivered per run. Source of truth for the rules.
- **Agent:** one `investigate` loop with its own mission and result schema on one tab.
- **Resolver:** one `ask_json` call without a browser that applies the rules to kept evidence.
- **Evidence:** a page kept word for word. Only evidence reaches the resolvers and `erp.extract`.
- **Test run / submission:** a test run shows points per field and doesn't count; a submission is reviewed and
  scored. The *latest* passed submission goes into the final, not the best one.

## Ways to hurt yourself

- Qwen sometimes sends `finish` as a string with broken JSON. `investigate` refuses it while time allows (an agent
  without a `check` only once, then the text is kept as `summary`); a result that still arrives broken loses its fields (a position without material is then omitted, not `no_bid`). A `finish`
  whose fields come without the `result` wrapper is taken as the result.
- `no_bid` only follows an explicit `no_match` from the ERP agent. Don't derive it from an empty field.
- Looking a website up by its `siteId`: ids and names differ in the private dataset. Use the roles from
  `resolvers.sites` (`tender_portal`, `supplier_portal`, `erp`, `webmail`).
- Putting public-1 values into a prompt "just as an example" is hardcoding.
- Leaving dev scripts that launch their own Chromium in the package: the reviewer sees them.
- A run that ends without an answer looks like a model failure but is usually a time problem: check the phase
  deadlines in `main` first.

## Keeping docs current

When an agent's behaviour changes, `docs/` changes in the same commit. When the phases, deadlines or data flow in
`agent.py` `main` change, the diagram in `README.md` changes with them. Point to code by file and function name, never
by line number. Delete what is outdated instead of marking it. How things came to be lives in the Entire
checkpoints, not in `docs/`. Everything in the repo is written in English.
