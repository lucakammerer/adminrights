# adminrights

Our agent system for the Atira hackathon challenge [`rfq`](https://ehl-challenge.atira.ai/challenges/rfq.md): it
turns a public tender into one signed bid. Four websites, 20 minutes, no human in the loop. Models decide where to go
and what matters; code reads pages, keeps evidence and does the arithmetic.

```mermaid
flowchart LR
  run([▶ Run]) --> roles

  subgraph P0["0 · Roles"]
    roles["🧭 Match sites<br/>to roles"]
  end

  subgraph P1["1 · Gather · ⏱ −10 min"]
    tender["🏛️ Tender portal<br/>positions · Q#amp;A"]
    supplier["📐 Supplier portal<br/>current spec"]
    mail["✉️ Webmail ×3<br/>approvals · terms"]
    login["🔑 ERP login"]
  end

  evidence[("📄 Kept<br/>evidence")]

  subgraph P2["2 · Interpret · ⏱ −6 min"]
    specs["🧠 Specs<br/>governing requirements"]
    req["🧠 Requirements<br/>quantities · specs"]
    com["🧠 Commercials<br/>discount · fees"]
  end

  subgraph P3["3 · Materials · ⏱ −6 min"]
    erp["🏭 ERP search<br/>one tab per spec, from Specs<br/>no match checked twice"]
    sweepnode["🔎 Gap sweep<br/>open commercial facts<br/>on the other sites"]
  end

  subgraph P4["4 · Calculate"]
    calc["🧮 calc.py<br/>exact arithmetic"]
  end

  subgraph P5["5 · Submit · ⏱ −20 s"]
    submit["✍️ Fill · read back<br/>sign with TAN from webmail"]
  end

  roles --> tender & supplier & mail & login
  tender & supplier & mail --> evidence
  evidence --> req & com
  supplier & mail -. as soon as done .-> specs --> erp
  req -. values Specs missed .-> erp
  req --> calc
  login -. session .-> erp
  erp --> calc
  com -. facts left open .-> sweepnode -. until ERP is done .-> calc
  com --> calc
  mail -. done: bidder data first .-> submit
  calc --> submit --> bid([✅ Bid])

  classDef browser fill:#dbeafe,stroke:#2563eb,color:#111827
  classDef model fill:#ede9fe,stroke:#7c3aed,color:#111827
  classDef code fill:#dcfce7,stroke:#16a34a,color:#111827
  classDef store fill:#fef3c7,stroke:#d97706,color:#111827
  classDef terminal fill:#111827,stroke:#111827,color:#ffffff
  class tender,supplier,mail,login,erp,sweepnode,submit browser
  class roles,specs,req,com model
  class calc code
  class evidence store
  class run,bid terminal
```

Blue: a model working a website in its own tab. Purple: a model call without a browser. Green: code. Times are hard
deadlines counted back from the end of the run's budget (at most 19 min); a phase cut at its deadline hands on what it
has. Source of truth: `main` in [`agent/agent.py`](agent/agent.py).

| Where | What |
| --- | --- |
| [`agent/`](agent/README.md) | The package we upload: orchestration, agents, browser tools, `calc.py` |
| [`docs/`](docs/README.md) | Rules we are judged by, the plan, one README per agent |
| `eval/`, `tests/`, `tools/` | Reference answers and scorer, tests, dev helpers; stay local |

```sh
atira models proxy                                  # terminal 1, keep it open
cd agent && eval "$(atira scout --env)"             # terminal 2
HEADLESS=1 uv run --no-sync python agent.py         # one local run
tools/score.sh                                      # from the repo root: local dry run with points per field
atira test-run .                                    # sandbox run with points per field
```
