# RFQ agent

Turns the Atira "From RFQ to bid" tender into one signed bid. Models do the navigating and deciding; code only reads
pages, keeps what the models select and does the brief's arithmetic.

1. **Investigate** (parallel, one browser each): a Qwen tool-loop works the tender portal, the supplier portal and
   the mailbox, keeping the pages it judges relevant as evidence; a fourth logs in to the ERP.
2. **Resolve**: two model calls apply the brief's rules to the kept evidence: final quantities and governing
   requirements, and the commercial keys (discount, clause groups, tariffs, commitments, pool, bonus, FX, index).
3. **Materials**: one ERP agent per distinct requirement picks the matching active material and keeps its pages;
   a model reads the facts from those pages and the agent is sent back if any are missing.
4. **Calculate**: `calc.py` applies the bid rules (scales, FX, clause discounts, shared stock, commitments,
   packaging, setup pool, project bonus, rounding).
5. **Submit**: a model fills the portal's bid wizard and signs it with the TAN another model finds in the mailbox.

| File | What it does |
| --- | --- |
| `agent.py` | Orchestration: phases, deadlines, data flow |
| `agents/<name>/` | One folder per agent: `agent.py` (mission, schema, `run`) and `README.md` (its docs) |
| `agents/common.py` | Shared system prompt, brief context, brief parser (reference, mail records), schema helpers |
| `validate.py` | Checks in code on what the models found (material attributes) |
| `llm.py` | The tool loop on the hosted Qwen |
| `browser.py`, `reader.js` | Browser tools; pages as accessible text with control refs |
| `calc.py` | Facts assembly and the bid arithmetic |
| `run.py`, `browsers.py` | Run contract and browsers (starter kit) |

```sh
atira models proxy                       # terminal 1
eval "$(atira scout --env)"              # terminal 2
HEADLESS=1 uv run --no-sync python agent.py
atira test-run .
```
