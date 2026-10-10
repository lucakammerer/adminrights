# adminrights

Team AdminRights' agent system for the Atira hackathon challenge
[From RFQ to bid](https://ehl-challenge.atira.ai/challenges/rfq.md): it reads a public tender across four websites
and enters one priced, signed bid, with no human in the loop. Rules, plan and work split live in [docs/](docs/README.md).

## Model flow

```mermaid
flowchart LR
    START(("▶ Run"))

    subgraph P0["0 · Roles"]
        SITES["🧭 Match sites<br/>to roles"]
    end

    subgraph P1["1 · Gather · ⏱ −10 min"]
        TEN["🏛️ Tender portal<br/>positions · Q&A"]
        SUP["📐 Supplier portal<br/>current spec"]
        WEB["✉️ Webmail<br/>approvals · terms"]
        LOG["🔑 ERP login"]
    end

    EV[("📄 Kept<br/>evidence")]

    subgraph P2["2 · Interpret · ⏱ −8 min"]
        REQ["🧠 Requirements<br/>quantities · specs"]
        COM["🧠 Commercials<br/>discount · fees"]
    end

    subgraph P3["3 · Materials · ⏱ −6 min"]
        ERP["🏭 ERP search<br/>one tab per spec"]
    end

    subgraph P4["4 · Calculate"]
        CALC["🧮 calc.py<br/>exact arithmetic"]
    end

    subgraph P5["5 · Submit · ⏱ −20 s"]
        SUB["✍️ Fill & sign<br/>TAN from webmail"]
    end

    DONE(("✅ Bid"))

    START --> SITES
    SITES --> TEN & SUP & WEB & LOG
    TEN & SUP & WEB --> EV
    EV --> REQ & COM
    REQ --> ERP
    LOG -. session .-> ERP
    ERP --> CALC
    COM --> CALC
    CALC --> SUB
    SUB --> DONE

    classDef agent fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#0f172a
    classDef model fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#0f172a
    classDef code fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a
    classDef store fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
    classDef edge fill:#0f172a,stroke:#0f172a,color:#ffffff

    class TEN,SUP,WEB,LOG,ERP,SUB agent
    class SITES,REQ,COM model
    class CALC code
    class EV store
    class START,DONE edge

    style P0 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
    style P1 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
    style P2 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
    style P3 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
    style P4 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
    style P5 fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#334155
```

🟦 browser agent (a model clicks, searches and keeps pages) · 🟪 single model call on the kept evidence ·
🟩 code · ⏱ hard cut, measured back from the end of the run budget (19 min)
