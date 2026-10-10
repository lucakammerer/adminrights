# docs

What the system *is* and how we build it: rules, plan and every agent. How it came to be lives in the Entire
checkpoints.

| File | Contents |
| --- | --- |
| [challenge.md](challenge.md) | Challenge frame: time, models, scoring, fair play |
| [RULES.md](RULES.md) | Every rule we are judged by: fair play, run validity, the 29 bid rules with where they live and their status, the Definition of Done |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | The system today (run outline, tool loop, agents), the target, the backlog, process and work split |
| [calc.md](calc.md) | Facts assembly and the arithmetic |
| [release.md](release.md) | Test loop, gates, run log, submission gate |
| [PLAN_COMPARISON.md](PLAN_COMPARISON.md) | Why the plan looks like this: evidence and verdicts from the merge (delete once read) |
| [platform/](platform/) | Dated copies of the platform docs: API, CLI, fair play, run contract, scoring, submitting, building an agent |

Public-1 values (scouting notes, logins, reference answers) live in [`../eval/`](../eval/), never here.

Each agent documents itself next to its code, in `agent/agents/<name>/README.md`:

| Agent | Contents |
| --- | --- |
| [tender_portal](../agent/agents/tender_portal/README.md) | Tender portal: positions and Q&A |
| [supplier_portal](../agent/agents/supplier_portal/README.md) | Supplier portal: current revision and requirements |
| [webmail](../agent/agents/webmail/README.md) | Webmail: approvals and condition mails |
| [erp](../agent/agents/erp/README.md) | ERP: login, material per requirement, fact extraction |
| [resolvers](../agent/agents/resolvers/README.md) | Requirements and commercial terms from the evidence |
| [sweep](../agent/agents/sweep/README.md) | Gap sweep: facts the first pass left open, looked for on the other sites |
| [submit](../agent/agents/submit/README.md) | Configurator, TAN, signing |

## Every agent README has the same sections

1. **Mission:** what the agent has to achieve, in two sentences
2. **Rules:** which bid rules (numbers from [RULES.md](RULES.md)) it covers
3. **Input / output:** what it receives and which schema it returns
4. **Implementation:** file, function, limits
5. **Pitfalls:** what goes wrong on the websites and how the mission handles it
6. **Open:** known gaps; done means delete

## Rules for these docs

- No values from public-1 (references, material numbers, prices, names). Describe observations in general terms.
- Link code by `file.py` + function name, never by line number.
- Change docs and code in the same commit. Delete what is no longer true.
- Keep it short. Don't retell what the code already says clearly.
- English only.
