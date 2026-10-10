# docs

What the system *is*: rules, architecture and every agent. How it came to be lives in the Entire checkpoints.

| File | Contents |
| --- | --- |
| [challenge.md](challenge.md) | Challenge frame: time, models, scoring, fair play |
| [architecture.md](architecture.md) | Phases, deadlines, data flow, the tool loop |
| [rules.md](rules.md) | The 29 bid rules: who implements them, where in the code, status |
| [calc.md](calc.md) | Facts assembly and the arithmetic |

Each agent documents itself next to its code, in `agent/agents/<name>/README.md`:

| Agent | Contents |
| --- | --- |
| [tender_portal](../agent/agents/tender_portal/README.md) | Tender portal: positions and Q&A |
| [supplier_portal](../agent/agents/supplier_portal/README.md) | Supplier portal: current revision and requirements |
| [webmail](../agent/agents/webmail/README.md) | Webmail: approvals and condition mails |
| [erp](../agent/agents/erp/README.md) | ERP: login, material per requirement, fact extraction |
| [resolvers](../agent/agents/resolvers/README.md) | Requirements and commercial terms from the evidence |
| [submit](../agent/agents/submit/README.md) | Configurator, TAN, signing |

## Every agent README has the same sections

1. **Mission:** what the agent has to achieve, in two sentences
2. **Rules:** which bid rules (numbers from [rules.md](rules.md)) it covers
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
